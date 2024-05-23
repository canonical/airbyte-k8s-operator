#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
from pathlib import Path

import ops
from charms.data_platform_libs.v0.data_models import TypedCharmBase
from log import log_event_handler
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from state import State
from structured_config import CharmConfig

logger = logging.getLogger(__name__)

CONTAINERS = [
    "airbyte-api-server",
    "airbyte-bootloader",
    "airbyte-connector-builder-server",
    "airbyte-cron",
    "airbyte-pod-sweeper",
    "airbyte-server",
    "airbyte-worker",
]
CONNECTOR_BUILDER_SERVER_API_PORT = 80
INTERNAL_API_PORT = 8001
AIRBYTE_API_PORT = 8006
WORKLOAD_API_PORT = 8007

# TODO (kelkawi-a): perform up check on the following ports for each container
# airbyte-api-server: 8006
# airbyte-bootloader: None
# airbyte-connector-builder-server: 8080
# airbyte-cron: 9001
# airbyte-pod-sweeper: None
# airbyte-server: 8001
# airbyte-worker: 9000


def get_pebble_layer(application_name, context):
    if application_name == "airbyte-worker":
        application_name = "airbyte-workers"

    command = f"/bin/bash -c airbyte-app/bin/{application_name}"
    if application_name == "airbyte-pod-sweeper":
        command = "./pod-sweeper.sh"

    return {
        "summary": "airbyte layer",
        "services": {
            application_name: {
                "summary": application_name,
                "command": command,
                "startup": "enabled",
                "override": "replace",
                # Including config values here so that a change in the
                # config forces replanning to restart the service.
                "environment": context,
            },
        },
    }


class AirbyteK8SOperatorCharm(TypedCharmBase[CharmConfig]):
    """Charm the application."""

    config_type = CharmConfig

    def __init__(self, *args):
        super().__init__(*args)
        self._state = State(self.app, lambda: self.model.get_relation("peer"))

        self.framework.observe(self.on.config_changed, self._on_config_changed)

        for container in CONTAINERS:
            self.framework.observe(self.on[container].pebble_ready, self._on_pebble_ready)

    @log_event_handler(logger)
    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Handle pebble-ready event."""
        self._update(event)

    @log_event_handler(logger)
    def _on_config_changed(self, event):
        """Handle changed configuration.

        Args:
            event: The event triggered when the relation changed.
        """
        self.unit.status = WaitingStatus("configuring application")
        self._update(event)

    # TODO (kelkawi-a): Potentially move this to helpers.py later on
    def _create_env(self):
        db_conn = self._state.database_connections["db"]

        host = db_conn["host"]
        port = db_conn["port"]
        db_name = db_conn["dbname"]
        db_url = f"jdbc:postgresql://{host}:{port}/{db_name}"

        # TODO (kelkawi-a): modify some of these values to grab data from relations instead
        return {
            "API_URL": "/api/v1/",
            "AIRBYTE_VERSION": "0.57.3",
            "AIRBYTE_EDITION": "community",
            "AUTO_DETECT_SCHEMA": "true",
            "DATABASE_URL": db_url,
            "DATABASE_USER": db_conn["user"],
            "DATABASE_PASSWORD": db_conn["password"],
            "DATABASE_DB": db_name,
            "DATABASE_HOST": host,
            "DATABASE_PORT": port,
            "WORKSPACE_ROOT": "/workspace",
            "CONFIG_ROOT": "/configs",
            "TEMPORAL_HOST": self.config["temporal-host"],
            "WORKER_LOGS_STORAGE_TYPE": self.config["storage-type"].value,
            "WORKER_STATE_STORAGE_TYPE": self.config["storage-type"].value,
            "STORAGE_TYPE": self.config["storage-type"].value,
            "STORAGE_BUCKET_ACTIVITY_PAYLOAD": "payload-storage",
            "STORAGE_BUCKET_LOG": self.config["storage-bucket-log"],
            "STORAGE_BUCKET_STATE": self.config["storage-bucket-state"],
            "STORAGE_BUCKET_WORKLOAD_OUTPUT": self.config["storage-bucket-workload-output"],
            "CONFIGS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.40.23.002",
            "JOBS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.40.26.001",
            "MICRONAUT_ENVIRONMENTS": "control-plane",
            "WORKERS_MICRONAUT_ENVIRONMENTS": "control-plane",
            "CRON_MICRONAUT_ENVIRONMENTS": "control-plane",
            "INTERNAL_API_HOST": f"localhost:{INTERNAL_API_PORT}",
            "LOG_LEVEL": self.config["log-level"].value,
            "MICROMETER_METRICS_ENABLED": "false",
            "KEYCLOAK_INTERNAL_HOST": "localhost",
            "KEYCLOAK_DATABASE_URL": db_url + "?currentSchema=keycloak",
            "WEBAPP_URL": "airbyte-ui-k8s:8080",
            "WORKER_ENVIRONMENT": "kubernetes",
            "WORKSPACE_DOCKER_MOUNT": "airbyte_workspace",
            "SECRET_PERSISTENCE": "TESTING_CONFIG_DB_TABLE",
            "CONNECTOR_BUILDER_SERVER_API_HOST": f"localhost:{CONNECTOR_BUILDER_SERVER_API_PORT}",
            "S3_LOG_BUCKET_REGION": "",
            "MINIO_ENDPOINT": "http://minio:9000",
            "S3_LOG_BUCKET": "airbyte-dev-logs",
            "S3_PATH_STYLE_ACCESS": "true",
            "SHOULD_RUN_NOTIFY_WORKFLOWS": "true",
            "STATE_STORAGE_MINIO_ACCESS_KEY": "minio",
            "STATE_STORAGE_MINIO_SECRET_ACCESS_KEY": "minio123",
            "STATE_STORAGE_MINIO_BUCKET_NAME": "state-storage",
            "STATE_STORAGE_MINIO_ENDPOINT": "http://minio:9000",
            "AIRBYTE_API_HOST": "localhost:8006",
            "CONNECTOR_BUILDER_API_URL": "/connector-builder-api",
            "WORKLOAD_API_HOST": "localhost:8007",
            "WORKLOAD_API_URL": "localhost:8007",
            "TEMPORAL_WORKER_PORTS": "9001,9002,9003,9004,9005,9006,9007,9008,9009,9010,9011,9012,9013,9014,9015,9016,9017,9018,9019,9020,9021,9022,9023,9024,9025,9026,9027,9028,9029,9030",
            "AWS_ACCESS_KEY_ID": "minio",
            "AWS_SECRET_ACCESS_KEY": "minio123",
            "JOB_KUBE_SERVICEACCOUNT": "airbyte-k8s",
            "JOB_KUBE_NAMESPACE": "dev-airbyte",
            "RUNNING_TTL_MINUTES": self.config["pod-running-ttl-minutes"],
            "SUCCEEDED_TTL_MINUTES": self.config["pod-successful-ttl-minutes"],
            "UNSUCCESSFUL_TTL_MINUTES": self.config["pod-unsuccessful-ttl-minutes"],
            "HTTP_PROXY": "http://squid.internal:3128",
            "HTTPS_PROXY": "http://squid.internal:3128",
            "NO_PROXY": "127.0.0.1,localhost,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.canonical.com,.launchpad.net,.internal,.jujucharms.com,temporal-k8s,minio",
            "http_proxy": "http://squid.internal:3128",
            "https_proxy": "http://squid.internal:3128",
            "no_proxy": "10.0.0.0/8,localhost,127.0.0.1,.internal,.cluster.local,.local,.svc,airbyte-*,temporal-k8s,minio",
            "JAVA_TOOL_OPTIONS": "-Dhttp.proxyHost=squid.internal -Dhttp.proxyPort=3128 -Dhttps.proxyHost=squid.internal -Dhttps.proxyPort=3128 -Dhttp.nonProxyHosts=10.0.0.0|localhost|127.0.0.1|*.internal|*.cluster.local|*.local|*.svc|airbyte-*|temporal-k8s|minio",
            "JOB_DEFAULT_ENV_http_proxy": "http://squid.internal:3128",
            "JOB_DEFAULT_ENV_https_proxy": "http://squid.internal:3128",
            "JOB_DEFAULT_ENV_no_proxy": "127.0.0.1,localhost,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.canonical.com,.launchpad.net,.internal,.jujucharms.com,temporal-k8s,minio",
            "JOB_DEFAULT_ENV_HTTP_PROXY": "http://squid.internal:3128",
            "JOB_DEFAULT_ENV_HTTPS_PROXY": "http://squid.internal:3128",
            "JOB_DEFAULT_ENV_NO_PROXY": "127.0.0.1,localhost,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.canonical.com,.launchpad.net,.internal,.jujucharms.com,temporal-k8s,minio",
            "JOB_DEFAULT_ENV_JAVA_TOOL_OPTIONS": "-Dhttp.proxyHost=squid.internal -Dhttp.proxyPort=3128 -Dhttps.proxyHost=squid.internal -Dhttps.proxyPort=3128 -Dhttp.nonProxyHosts=10.0.0.0|localhost|127.0.0.1|*.internal|*.cluster.local|*.local|*.svc|airbyte-*|temporal-k8s|minio",
        }

    def _update(self, event):
        """Update the Temporal server configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        # TODO (kelkawi-a): populate database connection from PostgreSQL relation
        if not self._state.database_connections:
            self.unit.status = BlockedStatus("missing db relation")
            return

        env = self._create_env()
        self.model.unit.set_ports(CONNECTOR_BUILDER_SERVER_API_PORT)
        self.model.unit.set_ports(INTERNAL_API_PORT)

        for service in CONTAINERS:
            container = self.unit.get_container(service)
            if not container.can_connect():
                event.defer()
                return

            if service == "airbyte-pod-sweeper":
                script_path = Path(__file__).parent / "scripts/pod-sweeper.sh"

                with open(script_path, "r") as file_source:
                    logger.info("pushing pod-sweeper script...")
                    container.push(
                        "/pod-sweeper.sh", file_source, make_dirs=True, permissions=0o755
                    )

            pebble_layer = get_pebble_layer(service, env)
            container.add_layer(service, pebble_layer, combine=True)
            container.replan()

        self.unit.status = ActiveStatus()


if __name__ == "__main__":  # pragma: nocover
    ops.main(AirbyteK8SOperatorCharm)  # type: ignore
