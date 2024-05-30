#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
from pathlib import Path

import ops
from botocore.exceptions import ClientError
from charm_helpers import create_env
from charms.data_platform_libs.v0.data_models import TypedCharmBase
from charms.data_platform_libs.v0.database_requires import DatabaseRequires
from charms.data_platform_libs.v0.s3 import S3Requirer
from literals import (
    BUCKET_CONFIGS,
    CONNECTOR_BUILDER_SERVER_API_PORT,
    CONTAINERS,
    INTERNAL_API_PORT,
    LOGS_BUCKET_CONFIG,
    REQUIRED_S3_PARAMETERS,
)
from log import log_event_handler
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from relations.airbyte_ui import AirbyteServer
from relations.minio import MinioRelation
from relations.postgresql import PostgresqlRelation
from relations.s3 import S3Integrator
from s3_helpers import S3Client
from state import State
from structured_config import CharmConfig, StorageType

logger = logging.getLogger(__name__)


def get_pebble_layer(application_name, context):
    return {
        "summary": "airbyte layer",
        "services": {
            application_name: {
                "summary": application_name,
                "command": f"/bin/bash -c airbyte-app/bin/{application_name}",
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
        self.framework.observe(self.on.peer_relation_changed, self._on_peer_relation_changed)

        # Handle postgresql relation.
        self.db = DatabaseRequires(
            self, relation_name="db", database_name="airbyte-k8s_db", extra_user_roles="admin"
        )
        self.postgresql = PostgresqlRelation(self)

        self.minio = MinioRelation(self)

        # Handle S3 integrator relation
        self.s3_client = S3Requirer(self, "s3-parameters")
        self.s3_relation = S3Integrator(self)

        # Handle UI relation
        self.airbyte_ui = AirbyteServer(self)

        for container in list(CONTAINERS.keys()):
            self.framework.observe(self.on[container].pebble_ready, self._on_pebble_ready)

    @log_event_handler(logger)
    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Handle pebble-ready event."""
        self._update(event)

    @log_event_handler(logger)
    def _on_peer_relation_changed(self, event):
        """Handle peer relation changed event.

        Args:
            event: The event triggered when the relation changed.
        """
        self._update(event)

    @log_event_handler(logger)
    def _on_config_changed(self, event):
        """Handle changed configuration.

        Args:
            event: The event triggered when the relation changed.
        """
        self.unit.status = WaitingStatus("configuring application")
        self._update(event)

    def _check_missing_params(self, params, required_params):
        """Validate that all required properties were extracted.

        Args:
            params: dictionary of parameters extracted from relation.
            required_params: list of required parameters.

        Returns:
            list: List of required parameters that are not set in state.
        """
        missing_params = []
        for key in required_params:
            if params.get(key) is None:
                missing_params.append(key)
        return missing_params

    def _validate(self):
        """Validate that configuration and relations are valid and ready.

        Raises:
            ValueError: in case of invalid configuration.
        """
        # Validate peer relation
        if not self._state.is_ready():
            raise ValueError("peer relation not ready")

        # Validate db relation
        if self._state.database_connection is None:
            raise ValueError("database relation not ready")

        # Validate minio relation
        if self.config["storage-type"] == StorageType.minio and self._state.minio is None:
            raise ValueError("minio relation not ready")

        # Validate S3 relation
        if self.config["storage-type"] == StorageType.s3 and self._state.s3 is None:
            raise ValueError("s3 relation not ready")

        # Validate S3 relation.
        if self._state.s3:
            missing_params = self._check_missing_params(self._state.s3, REQUIRED_S3_PARAMETERS)
            if len(missing_params) > 0:
                raise ValueError(f"s3:missing parameters {missing_params!r}")

    def _update(self, event):
        """Update the Temporal server configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        try:
            self._validate()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        s3_parameters = self._state.s3
        if self.config["storage-type"] == StorageType.minio:
            s3_parameters = self._state.minio

        try:
            s3_client = S3Client(s3_parameters)

            for bucket_config in BUCKET_CONFIGS:
                bucket = self.config[bucket_config]
                s3_client.create_bucket_if_not_exists(bucket)

            logs_ttl = int(self.config["logs-ttl"])
            s3_client.set_bucket_lifecycle_policy(
                bucket=self.config[LOGS_BUCKET_CONFIG], ttl=logs_ttl
            )
        except (ClientError, ValueError) as e:
            logging.info(f"Error creating bucket and setting lifecycle policy: {e}")
            self.unit.status = BlockedStatus(f"failed to create buckets: {str(e)}")
            return

        env = create_env(self.model.name, self.app.name, self.config, self._state)
        self.model.unit.set_ports(INTERNAL_API_PORT, CONNECTOR_BUILDER_SERVER_API_PORT)

        for service in list(CONTAINERS.keys()):
            container = self.unit.get_container(service)
            if not container.can_connect():
                event.defer()
                return

            if service == "airbyte-pod-sweeper":
                script_path = Path(__file__).parent / "scripts/pod-sweeper.sh"

                with open(script_path, "r") as file_source:
                    logger.info("pushing pod-sweeper script...")
                    container.push(
                        f"/airbyte-app/bin/{service}",
                        file_source,
                        make_dirs=True,
                        permissions=0o755,
                    )

            pebble_layer = get_pebble_layer(service, env)
            container.add_layer(service, pebble_layer, combine=True)
            container.replan()

        self.unit.status = ActiveStatus()
        if self.unit.is_leader():
            self.airbyte_ui._provide_server_status()


if __name__ == "__main__":  # pragma: nocover
    ops.main(AirbyteK8SOperatorCharm)  # type: ignore
