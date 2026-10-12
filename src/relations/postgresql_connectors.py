# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Provision Airbyte sources and destinations from postgresql_client relations."""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

import ops
import yaml
from ops import framework
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from airbyte_client import AirbyteAPIError, AirbyteClient
from log import log_event_handler

logger = logging.getLogger(__name__)

SOURCE_ENDPOINT = "postgresql-source"
DESTINATION_ENDPOINT = "postgresql-destination"
# Relation endpoint -> Airbyte connector type.
ENDPOINT_TYPES = {SOURCE_ENDPOINT: "source", DESTINATION_ENDPOINT: "destination"}
CONFIG_OPTIONS = {"source": "postgresql-source-config", "destination": "postgresql-destination-config"}
# Sources read from replicas when available; destinations always write to the primary.
TARGET_SERVER_TYPES = {"source": "preferSecondary", "destination": "primary"}

PEER_RELATION = "airbyte-peer"
MANAGED_CONNECTORS_KEY = "managed-connectors"
REQUESTED_SECRETS = ["username", "password", "tls", "tls-ca"]


class _ConnectorConfig(BaseModel):
    """Settings shared by source and destination config entries.

    Attrs:
        model_config: pydantic model configuration.
        database_prefix: prefix requested from PostgreSQL; must end with `*`.
        name: connector name template with `{app}` and `{database}` placeholders.
        jdbc_url_params: extra JDBC parameters, appended to the charm-managed ones.
        workspace: workspace name; the first workspace is used when not set.
    """

    model_config = ConfigDict(extra="forbid")

    database_prefix: str
    name: str = "{app}-{database}"
    jdbc_url_params: str = ""
    workspace: str | None = None

    @field_validator("database_prefix")
    @classmethod
    def prefix_ends_with_asterisk(cls, value: str) -> str:
        """Check that the database prefix ends with `*`.

        Args:
            value: the database prefix.

        Returns:
            The validated prefix.

        Raises:
            ValueError: if the prefix does not end with `*`.
        """
        if len(value) < 2 or not value.endswith("*"):
            raise ValueError("database_prefix must end with '*'")
        return value

    @field_validator("name")
    @classmethod
    def name_is_valid_template(cls, value: str) -> str:
        """Check that the name only uses the supported placeholders.

        Args:
            value: the name template.

        Returns:
            The validated template.

        Raises:
            ValueError: if the template uses unknown placeholders.
        """
        try:
            value.format(app="app", database="database")
        except (KeyError, IndexError, ValueError) as err:
            raise ValueError("name only supports the {app} and {database} placeholders") from err
        return value


class SourceConfig(_ConnectorConfig):
    """A `postgresql-source-config` entry.

    Attrs:
        schemas: schemas to replicate.
        replication_method: Airbyte replication method.
    """

    schemas: list[str] = ["public"]
    replication_method: Literal["Standard", "Xmin"] = "Standard"


class DestinationConfig(_ConnectorConfig):
    """A `postgresql-destination-config` entry.

    Attrs:
        destination_schema: default schema to write to.
        raw_data_schema: schema for raw tables, Airbyte default when not set.
        disable_type_dedupe: whether to disable typing and deduping.
    """

    destination_schema: str = Field("public", alias="schema")
    raw_data_schema: str | None = None
    disable_type_dedupe: bool | None = None


CONFIG_MODELS: dict[str, type[_ConnectorConfig]] = {"source": SourceConfig, "destination": DestinationConfig}


@dataclass(frozen=True)
class ProviderData:
    """Connection details published by the PostgreSQL provider.

    Attrs:
        endpoints: primary endpoints as comma-separated `host:port`.
        read_only_endpoints: replica endpoints as comma-separated `host:port`.
        databases: databases matched by the requested prefix.
        username: relation user name.
        password: relation user password.
        tls: whether the server requires TLS.
        tls_ca: CA certificate for TLS, if provided.
    """

    endpoints: str
    read_only_endpoints: str
    databases: list[str]
    username: str
    password: str
    tls: bool
    tls_ca: str | None


@dataclass(frozen=True)
class WantedConnector:
    """A connector the charm should manage, derived from relations and config.

    Attrs:
        connector_type: "source" or "destination".
        app: the PostgreSQL application name.
        database: the matched database.
        name: the connector name.
        workspace: the workspace name, or None for the first workspace.
        configuration: the Airbyte connector configuration.
        key: identifier of the connector in the tracked state.
        hash: hash of everything sent to Airbyte, used to detect changes.
    """

    connector_type: str
    app: str
    database: str
    name: str
    workspace: str | None
    configuration: dict = field(hash=False)

    @property
    def key(self) -> str:
        """Identifier of the connector in the tracked state."""
        return f"{self.connector_type}:{self.app}:{self.database}"

    @property
    def hash(self) -> str:
        """Hash of everything sent to Airbyte, used to detect changes."""
        payload = {"name": self.name, "workspace": self.workspace, "configuration": self.configuration}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_host(endpoints: list[str]) -> tuple[str, int]:
    """Build the multi-host `host` and `port` fields from `host:port` endpoints.

    The connectors format `jdbc:postgresql://{host}:{port}/{db}`, so every host
    but the last carries its own port and the last one uses `port`.

    Args:
        endpoints: `host:port` entries.

    Returns:
        The comma-separated host string and the port of the last host.
    """
    pairs = sorted({(host, int(port)) for host, port in (entry.rsplit(":", 1) for entry in endpoints)})
    *others, (last_host, last_port) = pairs
    return ",".join([f"{host}:{port}" for host, port in others] + [last_host]), last_port


def merge_jdbc_params(target_server_type: str, user_params: str) -> str:
    """Prepend the charm-managed targetServerType to the user's JDBC parameters.

    Args:
        target_server_type: the targetServerType the charm enforces.
        user_params: user-supplied `key=value&...` parameters.

    Returns:
        The merged parameters; a user-supplied targetServerType is dropped.
    """
    params = [f"targetServerType={target_server_type}"]
    for param in user_params.split("&"):
        param = param.strip()
        if not param:
            continue
        if param.split("=", 1)[0].strip().lower() == "targetservertype":
            logger.warning("Ignoring %r in jdbc_url_params: targetServerType is managed by the charm", param)
            continue
        params.append(param)
    return "&".join(params)


def build_configuration(connector_type: str, entry: _ConnectorConfig, provider: ProviderData, database: str) -> dict:
    """Build the Airbyte configuration for a Postgres source or destination.

    Args:
        connector_type: "source" or "destination".
        entry: the validated config entry for the relation.
        provider: the provider's connection details.
        database: the matched database.

    Returns:
        The connector configuration.
    """
    entries = [e.strip() for e in f"{provider.endpoints},{provider.read_only_endpoints}".split(",") if e.strip()]
    host, port = build_host(entries)

    if not provider.tls:
        ssl_mode: dict = {"mode": "disable"}
    elif provider.tls_ca:
        ssl_mode = {"mode": "verify-ca", "ca_certificate": provider.tls_ca}
    else:
        ssl_mode = {"mode": "require"}

    configuration: dict = {
        "host": host,
        "port": port,
        "database": database,
        "username": provider.username,
        "password": provider.password,
        "ssl_mode": ssl_mode,
        "tunnel_method": {"tunnel_method": "NO_TUNNEL"},
        "jdbc_url_params": merge_jdbc_params(TARGET_SERVER_TYPES[connector_type], entry.jdbc_url_params),
    }

    if isinstance(entry, SourceConfig):
        configuration["sourceType"] = "postgres"
        configuration["schemas"] = entry.schemas
        configuration["replication_method"] = {"method": entry.replication_method}
    elif isinstance(entry, DestinationConfig):
        configuration["destinationType"] = "postgres"
        configuration["schema"] = entry.destination_schema
        if entry.raw_data_schema:
            configuration["raw_data_schema"] = entry.raw_data_schema
        if entry.disable_type_dedupe is not None:
            configuration["disable_type_dedupe"] = entry.disable_type_dedupe
    return configuration


class PostgresqlConnectors(framework.Object):
    """Manage Airbyte connectors for the postgresql-source/destination relations."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "postgresql-connectors")
        self.charm = charm
        self.client = AirbyteClient()

        for endpoint in ENDPOINT_TYPES:
            charm.framework.observe(charm.on[endpoint].relation_created, self._on_relation_event)
            charm.framework.observe(charm.on[endpoint].relation_changed, self._on_relation_event)
            charm.framework.observe(charm.on[endpoint].relation_broken, self._on_relation_event)
        charm.framework.observe(charm.on.list_managed_connectors_action, self._on_list_managed_connectors)

    @log_event_handler(logger)
    def _on_relation_event(self, event: ops.RelationEvent) -> None:
        """Reconcile on any postgresql-source/destination relation change.

        Args:
            event: The relation event.
        """
        self.charm.reconcile()

    def reconcile(self) -> None:
        """Converge Airbyte connectors to the state described by relations and config.

        Runs on the leader only. Never changes the unit status: errors are
        logged and the affected connector is retried on the next reconcile.
        """
        if not self.charm.unit.is_leader():
            return

        entries = {connector_type: self._load_config(connector_type) for connector_type in CONFIG_OPTIONS}
        self._write_databags(entries)

        tracked = self._load_tracked()
        wanted = self._compute_wanted(entries)
        if not wanted and not tracked:
            return

        if not self.client.is_healthy():
            logger.info("Airbyte server not ready, skipping postgresql connector reconciliation")
            return

        workspaces: dict[str | None, str] = {}
        for key, connector in wanted.items():
            try:
                tracked[key] = self._apply(connector, tracked.get(key), workspaces)
            except AirbyteAPIError as err:
                logger.error("Failed to reconcile %s connector %r: %s", connector.connector_type, connector.name, err)
            self._save_tracked(tracked)

        self._mark_orphans(tracked, wanted)
        self._save_tracked(tracked)

    def _mark_orphans(self, tracked: dict[str, dict], wanted: dict[str, WantedConnector]) -> None:
        """Flag tracked connectors that are no longer wanted, untracking deleted ones.

        Args:
            tracked: tracked records keyed by connector key, updated in place.
            wanted: wanted connectors keyed by connector key.
        """
        for key in [key for key in tracked if key not in wanted]:
            record = tracked[key]
            try:
                exists = self.client.get_connector(record["type"], record["id"]) is not None
            except AirbyteAPIError as err:
                logger.error("Failed to look up orphaned connector %s: %s", record["id"], err)
                continue
            if not exists:
                logger.info("Orphaned %s %s was deleted, no longer tracking it", record["type"], record["id"])
                del tracked[key]
                continue
            record["orphaned"] = True
            logger.warning(
                "Orphaned %s %s (%s, database %r) is no longer managed; delete it manually if not needed",
                record["type"],
                record["id"],
                record["app"],
                record["database"],
            )

    def _apply(self, connector: WantedConnector, record: dict | None, workspaces: dict[str | None, str]) -> dict:
        """Create or update a single connector in Airbyte.

        Args:
            connector: the wanted connector.
            record: the tracked record for the connector, if any.
            workspaces: cache of workspace name to workspace ID.

        Returns:
            The updated tracked record.
        """
        if record and self.client.get_connector(connector.connector_type, record["id"]) is None:
            logger.info("%s %s no longer exists in Airbyte, recreating it", connector.connector_type, record["id"])
            record = None

        if record is None:
            if connector.workspace not in workspaces:
                workspaces[connector.workspace] = self.client.get_workspace_id(connector.workspace)
            connector_id = self.client.create_connector(
                connector.connector_type, workspaces[connector.workspace], connector.name, connector.configuration
            )
            logger.info("Created %s %r (%s)", connector.connector_type, connector.name, connector_id)
        elif record["hash"] != connector.hash or record.get("orphaned"):
            connector_id = record["id"]
            self.client.update_connector(
                connector.connector_type, connector_id, connector.name, connector.configuration
            )
            logger.info("Updated %s %r (%s)", connector.connector_type, connector.name, connector_id)
        else:
            return record

        return {
            "type": connector.connector_type,
            "app": connector.app,
            "database": connector.database,
            "id": connector_id,
            "hash": connector.hash,
            "orphaned": False,
        }

    def _load_config(self, connector_type: str) -> dict[str, _ConnectorConfig]:
        """Parse and validate a postgresql-*-config option.

        Args:
            connector_type: "source" or "destination".

        Returns:
            Valid entries keyed by PostgreSQL application name; invalid ones are
            logged and skipped.
        """
        option = CONFIG_OPTIONS[connector_type]
        raw = self.charm.config[option]
        if not raw:
            return {}
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as err:
            logger.error("%s is not valid YAML: %s", option, err)
            return {}
        if not isinstance(parsed, dict):
            logger.error("%s must be a mapping of application names to settings", option)
            return {}

        entries = {}
        for app, settings in parsed.items():
            try:
                entries[str(app)] = CONFIG_MODELS[connector_type].model_validate(settings or {})
            except ValidationError as err:
                logger.error("Invalid %s entry for %r: %s", option, app, err)
        return entries

    def _relations(self):
        """Yield the active relations on both endpoints with their connector type.

        Yields:
            (connector type, relation) pairs.
        """
        for endpoint, connector_type in ENDPOINT_TYPES.items():
            for relation in self.model.relations[endpoint]:
                if relation.active and relation.app is not None:
                    yield connector_type, relation

    def _write_databags(self, entries: dict[str, dict[str, _ConnectorConfig]]) -> None:
        """Request access to the configured database prefix on each relation.

        Args:
            entries: validated config entries per connector type.
        """
        for connector_type, relation in self._relations():
            entry = entries[connector_type].get(relation.app.name)
            if entry is None:
                logger.warning("No %s entry for %r", CONFIG_OPTIONS[connector_type], relation.app.name)
                continue
            databag = relation.data[self.charm.app]
            requested = databag.get("database")
            if requested and requested != entry.database_prefix:
                logger.warning(
                    "database_prefix for %r changed from %r to %r; re-create the relation to apply it",
                    relation.app.name,
                    requested,
                    entry.database_prefix,
                )
                continue
            if not requested:
                databag["database"] = entry.database_prefix
                databag["requested-secrets"] = json.dumps(REQUESTED_SECRETS)

    def _load_provider_data(self, relation: ops.Relation) -> ProviderData | None:
        """Read the provider's connection details, resolving its secrets.

        Args:
            relation: the relation to read from.

        Returns:
            The provider data, or None if not yet complete.
        """
        data = relation.data[relation.app]
        endpoints = data.get("endpoints")
        prefix_databases = data.get("prefix-databases")
        secret_user = data.get("secret-user")
        if not (endpoints and prefix_databases and secret_user):
            return None

        try:
            user = self.model.get_secret(id=secret_user).get_content(refresh=True)
            secret_tls = data.get("secret-tls")
            tls = self.model.get_secret(id=secret_tls).get_content(refresh=True) if secret_tls else {}
        except (ops.SecretNotFoundError, ops.ModelError) as err:
            logger.error("Could not read secrets for %r: %s", relation.app.name, err)
            return None

        return ProviderData(
            endpoints=endpoints,
            read_only_endpoints=data.get("read-only-endpoints", ""),
            databases=sorted({db.strip() for db in prefix_databases.split(",") if db.strip()}),
            username=user["username"],
            password=user["password"],
            tls=str(tls.get("tls", "false")).lower() == "true",
            tls_ca=tls.get("tls-ca") or None,
        )

    def _compute_wanted(self, entries: dict[str, dict[str, _ConnectorConfig]]) -> dict[str, WantedConnector]:
        """Compute the connectors that should exist from relations and config.

        Args:
            entries: validated config entries per connector type.

        Returns:
            Wanted connectors keyed by their tracked-state key.
        """
        wanted = {}
        for connector_type, relation in self._relations():
            app = relation.app.name
            entry = entries[connector_type].get(app)
            if entry is None:
                continue
            provider = self._load_provider_data(relation)
            if provider is None:
                logger.info("Relation data from %r not ready yet", app)
                continue
            for database in provider.databases:
                connector = WantedConnector(
                    connector_type=connector_type,
                    app=app,
                    database=database,
                    name=entry.name.format(app=app, database=database),
                    workspace=entry.workspace,
                    configuration=build_configuration(connector_type, entry, provider, database),
                )
                wanted[connector.key] = connector
        return wanted

    def _load_tracked(self) -> dict[str, dict]:
        """Return the tracked connectors from the peer relation.

        Returns:
            Tracked records keyed by connector key.
        """
        relation = self.model.get_relation(PEER_RELATION)
        if relation is None:
            return {}
        return json.loads(relation.data[self.charm.app].get(MANAGED_CONNECTORS_KEY, "{}"))

    def _save_tracked(self, tracked: dict[str, dict]) -> None:
        """Persist the tracked connectors in the peer relation.

        Args:
            tracked: tracked records keyed by connector key.
        """
        relation = self.model.get_relation(PEER_RELATION)
        if relation is None:
            return
        relation.data[self.charm.app][MANAGED_CONNECTORS_KEY] = json.dumps(tracked, sort_keys=True)

    @log_event_handler(logger)
    def _on_list_managed_connectors(self, event: ops.ActionEvent) -> None:
        """List managed connectors with their details fetched live from Airbyte.

        Args:
            event: The action event.
        """
        connector_type = event.params.get("type")
        connectors = []
        try:
            for record in self._load_tracked().values():
                if connector_type and record["type"] != connector_type:
                    continue
                connector = self.client.get_connector(record["type"], record["id"])
                if connector is None:
                    continue
                connectors.append(
                    {
                        "type": record["type"],
                        "id": record["id"],
                        "name": connector.get("name"),
                        "database": connector.get("configuration", {}).get("database"),
                        "app": record["app"],
                        "orphaned": record["orphaned"],
                    }
                )
        except AirbyteAPIError as err:
            event.fail(f"Airbyte API unavailable: {err}")
            return
        event.set_results({"connectors": json.dumps(connectors)})
