# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Provision Airbyte sources and destinations from postgresql_client relations."""

import json
import logging

import ops
import yaml
from ops import framework
from pydantic import ValidationError

from airbyte_client import AirbyteAPIError, AirbyteClient
from connector_configuration import ProviderData, WantedConnector, build_configuration
from literals import (
    CONNECTOR_CONFIG_OPTIONS,
    CONNECTOR_ENDPOINT_TYPES,
    CONNECTOR_EXTRA_USER_ROLES,
    CONNECTOR_REQUESTED_SECRETS,
    MANAGED_CONNECTORS_KEY,
    PEER_RELATION,
)
from log import log_event_handler
from structured_config import CONFIG_MODELS, ConnectorConfig

logger = logging.getLogger(__name__)


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

        for endpoint in CONNECTOR_ENDPOINT_TYPES:
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

        entries = {connector_type: self._load_config(connector_type) for connector_type in CONNECTOR_CONFIG_OPTIONS}
        self._write_databags(entries)

        tracked = self._load_tracked()
        wanted, skipped = self._compute_wanted(entries)
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

        self._mark_orphans(tracked, wanted, skipped)
        self._save_tracked(tracked)

    def _mark_orphans(
        self, tracked: dict[str, dict], wanted: dict[str, WantedConnector], skipped: set[tuple[str, str]]
    ) -> None:
        """Flag tracked connectors that are no longer wanted, untracking deleted ones.

        Args:
            tracked: tracked records keyed by connector key, updated in place.
            wanted: wanted connectors keyed by connector key.
            skipped: (type, app) of relations whose data could not be used; their
                connectors are left as they are until the data is usable again.
        """
        for key in [key for key in tracked if key not in wanted]:
            record = tracked[key]
            if (record["type"], record["app"]) in skipped:
                continue
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
        if connector.workspace not in workspaces:
            workspaces[connector.workspace] = self.client.get_workspace_id(connector.workspace)
        workspace_id = workspaces[connector.workspace]

        existing = self.client.get_connector(connector.connector_type, record["id"]) if record else None
        if record and existing is None:
            logger.info("%s %s no longer exists in Airbyte, recreating it", connector.connector_type, record["id"])
            record = None

        if existing and existing.get("workspaceId") != workspace_id:
            logger.warning(
                "%s %r (%s) is not in the configured workspace %r and cannot be moved; "
                "delete it in Airbyte to have it recreated there",
                connector.connector_type,
                connector.name,
                existing.get("workspaceId"),
                connector.workspace or "default",
            )

        if record is None:
            connector_id = self.client.create_connector(
                connector.connector_type, workspace_id, connector.name, connector.configuration
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

    def _load_config(self, connector_type: str) -> dict[str, ConnectorConfig]:
        """Parse and validate a postgresql-*-config option.

        Args:
            connector_type: "source" or "destination".

        Returns:
            Valid entries keyed by PostgreSQL application name; invalid ones are
            logged and skipped.
        """
        option = CONNECTOR_CONFIG_OPTIONS[connector_type]
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
        for endpoint, connector_type in CONNECTOR_ENDPOINT_TYPES.items():
            for relation in self.model.relations[endpoint]:
                if relation.active and relation.app is not None:
                    yield connector_type, relation

    def _write_databags(self, entries: dict[str, dict[str, ConnectorConfig]]) -> None:
        """Request access to the configured database prefix on each relation.

        Args:
            entries: validated config entries per connector type.
        """
        for connector_type, relation in self._relations():
            entry = entries[connector_type].get(relation.app.name)
            if entry is None:
                logger.warning("No %s entry for %r", CONNECTOR_CONFIG_OPTIONS[connector_type], relation.app.name)
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
                databag["requested-secrets"] = json.dumps(CONNECTOR_REQUESTED_SECRETS)
                if connector_type in CONNECTOR_EXTRA_USER_ROLES:
                    databag["extra-user-roles"] = CONNECTOR_EXTRA_USER_ROLES[connector_type]

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

    def _compute_wanted(
        self, entries: dict[str, dict[str, ConnectorConfig]]
    ) -> tuple[dict[str, WantedConnector], set[tuple[str, str]]]:
        """Compute the connectors that should exist from relations and config.

        A relation whose data is incomplete or malformed is skipped without
        affecting the others.

        Args:
            entries: validated config entries per connector type.

        Returns:
            Wanted connectors keyed by their tracked-state key, and the
            (type, app) of skipped relations.
        """
        wanted = {}
        skipped = set()
        for connector_type, relation in self._relations():
            app = relation.app.name
            entry = entries[connector_type].get(app)
            if entry is None:
                continue
            try:
                connectors = self._wanted_for_relation(connector_type, relation, entry)
            except (KeyError, ValueError) as err:
                logger.error("Skipping %s relation with %r: malformed relation data: %r", connector_type, app, err)
                connectors = None
            if connectors is None:
                skipped.add((connector_type, app))
                continue
            wanted.update({connector.key: connector for connector in connectors})
        return wanted, skipped

    def _wanted_for_relation(
        self, connector_type: str, relation: ops.Relation, entry: ConnectorConfig
    ) -> list[WantedConnector] | None:
        """Compute the connectors wanted for one relation.

        Args:
            connector_type: "source" or "destination".
            relation: the PostgreSQL relation.
            entry: the validated config entry for the relation.

        Returns:
            The wanted connectors, or None if the relation data is not ready yet.
        """
        app = relation.app.name
        provider = self._load_provider_data(relation)
        if provider is None:
            logger.info("Relation data from %r not ready yet", app)
            return None
        return [
            WantedConnector(
                connector_type=connector_type,
                app=app,
                database=database,
                name=entry.name.format(app=app, database=database),
                workspace=entry.workspace,
                configuration=build_configuration(connector_type, entry, provider, database),
            )
            for database in provider.databases
        ]

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
                        "database": (connector.get("configuration") or {}).get("database"),
                        "app": record["app"],
                        "orphaned": record["orphaned"],
                    }
                )
        except AirbyteAPIError as err:
            event.fail(f"Airbyte API unavailable: {err}")
            return
        event.set_results({"connectors": json.dumps(connectors)})
