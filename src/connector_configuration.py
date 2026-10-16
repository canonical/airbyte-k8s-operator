# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Build Airbyte Postgres connector configurations from relation data and config."""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import cached_property

from literals import TARGET_SERVER_TYPES
from structured_config import ConnectorConfig, DestinationConfig, SourceConfig

logger = logging.getLogger(__name__)


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
        hash: hash of the name and configuration, used to detect changes.
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

    @cached_property
    def hash(self) -> str:
        """Hash of the name and configuration, used to detect changes.

        The workspace is excluded: Airbyte cannot move a connector between workspaces.
        """
        payload = {"name": self.name, "configuration": self.configuration}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_host(endpoints: list[str]) -> tuple[str, int]:
    """Build the multi-host `host` and `port` fields from `host:port` endpoints.

    The connectors format `jdbc:postgresql://{host}:{port}/{db}`, so every host
    but the last carries its own port and the last one uses `port`.

    Args:
        endpoints: `host:port` entries.

    Returns:
        The comma-separated host string and the port of the last host.

    Raises:
        ValueError: if there are no endpoints or one is not `host:port`.
    """
    if not endpoints:
        raise ValueError("no endpoints")
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


def build_configuration(connector_type: str, entry: ConnectorConfig, provider: ProviderData, database: str) -> dict:
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
