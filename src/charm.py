#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""
import base64
import hashlib
import logging

import kubernetes.client
import ops
from botocore.exceptions import ClientError
from charms.data_platform_libs.v0.data_models import TypedCharmBase
from charms.data_platform_libs.v0.database_requires import DatabaseRequires
from charms.data_platform_libs.v0.s3 import S3Requirer
from kubernetes.client.exceptions import ApiException
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import CheckStatus

from charm_helpers import create_env
from literals import (
    AIRBYTE_API_PORT,
    AIRBYTE_AUTH_K8S_SECRET_NAME,
    AIRBYTE_VERSION,
    BUCKET_CONFIGS,
    CONNECTOR_BUILDER_SERVER_API_PORT,
    CONTAINER_HEALTH_CHECK_MAP,
    FLAGS_FILE_PATH,
    INTERNAL_API_PORT,
    LOGS_BUCKET_CONFIG,
    REQUIRED_S3_PARAMETERS,
    WORKLOAD_API_PORT,
    WORKLOAD_LAUNCHER_PORT,
)
from log import log_event_handler
from relations.airbyte_ui import AirbyteServerProvider
from relations.minio import MinioRelation
from relations.postgresql import PostgresqlRelation
from relations.s3 import S3Integrator
from s3_helpers import S3Client
from state import State
from structured_config import CharmConfig, StorageType
from utils import render_template, use_feature_flags

logger = logging.getLogger(__name__)


def get_pebble_layer(application_name, context):
    """Create pebble layer based on application.

    Args:
        application_name: Name of Airbyte application.
        context: environment to include with the pebble plan.

    Returns:
        pebble plan dict.
    """
    pebble_layer = {
        "summary": "airbyte layer",
        "services": {
            application_name: {
                "summary": application_name,
                "command": f"/bin/bash {application_name}/airbyte-app/bin/{application_name}",
                "startup": "enabled",
                "override": "replace",
                # Including config values here so that a change in the
                # config forces replanning to restart the service.
                "environment": context,
            },
        },
    }

    if application_name == "airbyte-bootloader":
        pebble_layer["services"][application_name].update(
            {
                "on-success": "ignore",
            }
        )

    application_info = CONTAINER_HEALTH_CHECK_MAP[application_name]
    if application_info is not None:
        pebble_layer["services"][application_name].update(
            {
                "on-check-failure": {"up": "ignore"},
            }
        )
        pebble_layer.update(
            {
                "checks": {
                    "up": {
                        "override": "replace",
                        "period": "10s",
                        "http": {
                            "url": f"http://localhost:{application_info['port']}{application_info['health_endpoint']}"
                        },
                    }
                }
            }
        )

    return pebble_layer


class AirbyteK8SOperatorCharm(TypedCharmBase[CharmConfig]):
    """Airbyte Server charm.

    Attrs:
        _state: used to store data that is persisted across invocations.
        config_type: the charm structured config
    """

    config_type = CharmConfig

    def __init__(self, *args):
        """Construct.

        Args:
            args: Ignore.
        """
        super().__init__(*args)
        kubernetes.config.load_incluster_config()
        self._k8s_client = kubernetes.client.CoreV1Api()

        self._state = State(self.app, lambda: self.model.get_relation("airbyte-peer"))

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.airbyte_peer_relation_changed, self._on_peer_relation_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)

        # Handle postgresql relation.
        self.db = DatabaseRequires(self, relation_name="db", database_name="airbyte-k8s_db", extra_user_roles="admin")
        self.postgresql = PostgresqlRelation(self)

        self.minio = MinioRelation(self)

        # Handle S3 integrator relation
        self.s3_client = S3Requirer(self, "s3-parameters")
        self.s3_relation = S3Integrator(self)

        # Handle UI relation
        self.airbyte_ui = AirbyteServerProvider(self)

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            self.framework.observe(self.on[container_name].pebble_ready, self._on_pebble_ready)

    @log_event_handler(logger)
    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Handle pebble ready event.

        Args:
            event: The event triggered.
        """
        self._update(event)

    @log_event_handler(logger)
    def _on_peer_relation_changed(self, event):
        """Handle peer relation changed event.

        Args:
            event: The event triggered when the relation changed.
        """
        self._update(event)

    @log_event_handler(logger)
    def _on_update_status(self, event):
        """Handle `update-status` events.

        Args:
            event: The `update-status` event triggered at intervals.
        """
        try:
            self._validate()
        except ValueError:
            return

        all_valid_plans = True
        for container_name, settings in CONTAINER_HEALTH_CHECK_MAP.items():
            if not settings:
                continue

            container = self.unit.get_container(container_name)
            valid_pebble_plan = self._validate_pebble_plan(container, container_name)
            logger.info(f"validating pebble plan for {container_name}")
            if not valid_pebble_plan:
                logger.debug(f"failed to validate pebble plan for {container_name}, attempting creation again")
                all_valid_plans = False
                continue

            logger.info(f"performing up check for {container_name}")
            check = container.get_check("up")
            if check.status != CheckStatus.UP:
                logger.error(f"check failed for {container_name}")
                self.unit.status = MaintenanceStatus(f"Status check: {container_name!r} DOWN")
                return

        if not all_valid_plans:
            self._update(event)
            return

        self.unit.set_workload_version(f"v{AIRBYTE_VERSION}")
        self.unit.status = ActiveStatus()
        if self.unit.is_leader():
            self.airbyte_ui._provide_server_status()

    def _validate_pebble_plan(self, container, container_name):
        """Validate pebble plan.

        Args:
            container: application container
            container_name: name of container to check

        Returns:
            bool of pebble plan validity
        """
        try:
            plan = container.get_plan().to_dict()
            return bool(plan["services"][container_name]["on-check-failure"])
        except (KeyError, ops.pebble.ConnectionError):
            return False

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

    def _generate_flags_yaml_content(self):
        """Generate flags.yaml content from opinionated config using Jinja2 template.

        Returns:
            str or None: The flags.yaml content as a string, or None if no flags are configured.
        """
        # Check if any flags are configured
        if not use_feature_flags(self.config):
            return None

        # Prepare template context
        context = {
            "heartbeat_max_seconds_between_messages": self.config["heartbeat-max-seconds-between-messages"],
            "heartbeat_fail_sync": self.config["heartbeat-fail-sync"],
            "destination_timeout_max_seconds": self.config["destination-timeout-max-seconds"],
            "destination_timeout_fail_sync": self.config["destination-timeout-fail-sync"],
        }

        # Render template
        return render_template("flags.jinja", context)

    def _push_flags_to_container(self, container, container_name, flags_yaml_content, env):
        """Push generated flags content to container if available.

        Args:
            container: The container to push flags to.
            container_name: Name of the container.
            flags_yaml_content: The flags YAML content to push, or None.
            env: Environment dictionary to update with flags hash.
        """
        if not flags_yaml_content:
            return

        try:
            # Airbyte ConfigFileClient reads a file at FEATURE_FLAG_PATH.
            # We set FEATURE_FLAG_PATH=/flags,
            # so write the YAML directly to the file path '/flags' (no extension).
            container.push(FLAGS_FILE_PATH, flags_yaml_content)
            logger.info("Pushed flags to %s at %s", container_name, FLAGS_FILE_PATH)
        except Exception as e:
            logger.error("Failed to push flags file to %s: %s", container_name, e)
            self.unit.status = BlockedStatus(f"failed to push flags file: {str(e)}")
            return

    def _add_flags_hash_to_env(self, flags_yaml_content, container_name, env):
        """Add a hash of flags content to env to force replan+restart when flags change."""
        try:
            flags_hash = hashlib.sha256(flags_yaml_content.encode("utf-8")).hexdigest()
            env.update({"FEATURE_FLAG_HASH": flags_hash})
        except Exception as e:
            logger.warning("Failed to compute flags hash for %s: %s", container_name, e)

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

    def _update(self, event):  # noqa: C901
        """Update configuration and replan its execution.

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
            s3_client.set_bucket_lifecycle_policy(bucket_name=self.config[LOGS_BUCKET_CONFIG], ttl=logs_ttl)
        except (ClientError, ValueError) as e:
            logger.error(f"Error creating bucket and setting lifecycle policy: {e}")
            self.unit.status = BlockedStatus(f"failed to create buckets: {str(e)}")
            return

        self.model.unit.set_ports(
            AIRBYTE_API_PORT,
            INTERNAL_API_PORT,
            CONNECTOR_BUILDER_SERVER_API_PORT,
            WORKLOAD_API_PORT,
            WORKLOAD_LAUNCHER_PORT,
        )

        flags_yaml_content = self._generate_flags_yaml_content()

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            container = self.unit.get_container(container_name)
            if not container.can_connect():
                event.defer()
                return

            env = create_env(self.model.name, self.app.name, container_name, self.config, self._state)
            env = {k: v for k, v in env.items() if v is not None}

            self._push_flags_to_container(container, container_name, flags_yaml_content, env)
            self._add_flags_hash_to_env(flags_yaml_content, container_name, env)

            # Read values from k8s secret created by airbyte-bootloader and add
            # them to the pebble plan.
            try:
                secret = self._k8s_client.read_namespaced_secret(AIRBYTE_AUTH_K8S_SECRET_NAME, self.model.name)
                decoded_data = {k: base64.b64decode(v).decode("utf-8") for k, v in secret.data.items()}

                if decoded_data.get("dataplane-client-id"):
                    env.update({"DATAPLANE_CLIENT_ID": decoded_data["dataplane-client-id"]})
                if decoded_data.get("dataplane-client-secret"):
                    env.update({"DATAPLANE_CLIENT_SECRET": decoded_data["dataplane-client-secret"]})

            except ApiException as e:
                if e.status == 404:
                    logging.info(
                        "Secret '%s' not found in namespace '%s'.", AIRBYTE_AUTH_K8S_SECRET_NAME, self.model.name
                    )
                else:
                    logging.error("Error: %s", str(e))

            pebble_layer = get_pebble_layer(container_name, env)
            container.add_layer(container_name, pebble_layer, combine=True)
            container.replan()

        self.unit.status = MaintenanceStatus("replanning application")


if __name__ == "__main__":  # pragma: nocover
    ops.main(AirbyteK8SOperatorCharm)  # type: ignore
