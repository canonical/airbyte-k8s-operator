#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""
import base64
import logging

import kubernetes.client
import ops
from botocore.exceptions import ClientError
from charms.data_platform_libs.v0.data_models import TypedCharmBase
from charms.data_platform_libs.v0.database_requires import DatabaseRequires
from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
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
from structured_config import CharmConfig, StorageType

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

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.airbyte_peer_relation_changed, self._on_peer_relation_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.secret_changed, self._on_secret_changed)

        # Handle postgresql relation.
        self.db = DatabaseRequires(self, relation_name="db", database_name="airbyte-k8s_db", extra_user_roles="admin")
        self.postgresql = PostgresqlRelation(self)

        self.minio = MinioRelation(self)

        # Handle S3 integrator relation
        self.s3_client = S3Requirer(self, "s3-parameters")
        self.s3_relation = S3Integrator(self)

        # Handle UI relation
        self.airbyte_ui = AirbyteServerProvider(self)

        # Airbyte server serves from the root of its backend, so strip_prefix=True
        # makes the ingress provider strip the per-app path prefix before forwarding.
        self.ingress = IngressPerAppRequirer(self, port=INTERNAL_API_PORT, strip_prefix=True)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            self.framework.observe(self.on[container_name].pebble_ready, self._on_pebble_ready)

    @log_event_handler(logger)
    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Handle pebble ready event.

        Args:
            event: The event triggered.
        """
        self.reconcile()

    @log_event_handler(logger)
    def _on_ingress_ready(self, event):
        """Handle the ingress-ready event.

        Args:
            event: The event triggered when the ingress URL becomes available.
        """
        self.reconcile()

    @log_event_handler(logger)
    def _on_ingress_revoked(self, event):
        """Handle the ingress-revoked event.

        Args:
            event: The event triggered when the ingress relation is removed.
        """
        self.reconcile()

    @log_event_handler(logger)
    def _on_peer_relation_changed(self, event):
        """Handle peer relation changed event.

        Args:
            event: The event triggered when the relation changed.
        """
        self.reconcile()

    @log_event_handler(logger)
    def _on_secret_changed(self, event):
        """Handle secret-changed events by reconciling.

        Args:
            event: The secret-changed event.
        """
        self.reconcile()

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
            self.reconcile()
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
        self.reconcile()

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

        Returns:
            Tuple of (db_connection, minio_connection, s3_connection, credentials)
            derived live from the model.

        Raises:
            ValueError: in case of invalid configuration.
        """
        # Validate peer relation
        if not self.model.get_relation("airbyte-peer"):
            raise ValueError("peer relation not ready")

        # Validate db relation
        db_connection = self.postgresql.get_data()
        if db_connection is None:
            raise ValueError("database relation not ready")

        minio_connection = self.minio.get_data()
        s3_connection = self.s3_relation.get_data()

        # Validate minio relation
        if self.config["storage-type"] == StorageType.minio and minio_connection is None:
            raise ValueError("minio relation not ready")

        # Validate S3 relation
        if self.config["storage-type"] == StorageType.s3 and s3_connection is None:
            raise ValueError("s3 relation not ready")

        if s3_connection:
            missing_params = self._check_missing_params(s3_connection, REQUIRED_S3_PARAMETERS)
            if len(missing_params) > 0:
                raise ValueError(f"s3:missing parameters {missing_params!r}")

        credentials = self._resolve_credentials()

        return db_connection, minio_connection, s3_connection, credentials

    def _resolve_credentials(self):
        """Resolve secret-backed credentials from Juju secrets.

        Returns:
            A dict of resolved credential values; empty when no credential
            secret is configured.
        """
        credentials = {}

        aws_secret_id = self.config["aws-credentials-secret-id"]
        if aws_secret_id:
            content = self._get_secret_content(aws_secret_id, ["aws-access-key", "aws-secret-access-key"])
            credentials["aws-access-key"] = content["aws-access-key"]
            credentials["aws-secret-access-key"] = content["aws-secret-access-key"]

        gcp_secret_id = self.config["gcp-credentials-secret-id"]
        if gcp_secret_id:
            content = self._get_secret_content(gcp_secret_id, ["secret-store-gcp-credentials"])
            credentials["secret-store-gcp-credentials"] = content["secret-store-gcp-credentials"]

        vault_secret_id = self.config["vault-token-secret-id"]
        if vault_secret_id:
            content = self._get_secret_content(vault_secret_id, ["vault-auth-token"])
            credentials["vault-auth-token"] = content["vault-auth-token"]

        return credentials

    def _get_secret_content(self, secret_id, required_keys):
        """Fetch and validate the content of a Juju secret.

        Args:
            secret_id: the Juju secret ID provided via config.
            required_keys: keys the secret content must contain.

        Returns:
            The secret content mapping.

        Raises:
            ValueError: if the secret is missing, inaccessible, or is missing
                any of the required keys.
        """
        try:
            content = self.model.get_secret(id=secret_id).get_content(refresh=True)
        except ops.SecretNotFoundError as err:
            raise ValueError(f"secret {secret_id!r} not found") from err
        except ops.ModelError as err:
            raise ValueError(
                f"secret {secret_id!r} not found or not granted to this app; "
                f"check the secret ID and run `juju grant-secret`"
            ) from err

        missing_keys = [key for key in required_keys if not content.get(key)]
        if missing_keys:
            raise ValueError(f"secret {secret_id!r} missing keys: {missing_keys!r}")

        return content

    def _get_auth_secret_env(self):
        """Return the dataplane env vars from the bootloader-created K8s secret.

        Returns:
            A mapping with DATAPLANE_CLIENT_ID/DATAPLANE_CLIENT_SECRET when the
            airbyte-auth-secrets secret exists and is populated, or an empty dict
            if it has not been created yet (the bootloader creates it on startup).
        """
        try:
            secret = self._k8s_client.read_namespaced_secret(AIRBYTE_AUTH_K8S_SECRET_NAME, self.model.name)
        except ApiException as err:
            if err.status == 404:
                logger.info("Secret %r not yet created in namespace %r", AIRBYTE_AUTH_K8S_SECRET_NAME, self.model.name)
            else:
                logger.error("Error reading secret %r: %s", AIRBYTE_AUTH_K8S_SECRET_NAME, str(err))
            return {}

        decoded = {k: base64.b64decode(v).decode("utf-8") for k, v in (secret.data or {}).items()}
        env = {}
        if decoded.get("dataplane-client-id"):
            env["DATAPLANE_CLIENT_ID"] = decoded["dataplane-client-id"]
        if decoded.get("dataplane-client-secret"):
            env["DATAPLANE_CLIENT_SECRET"] = decoded["dataplane-client-secret"]
        return env

    def reconcile(self):  # noqa: C901
        """Reconcile the charm to its desired state.

        Single entry point for every observer: derives the desired state from
        the current model (config + relations) and converges the workload
        toward it. Holds no persisted state of its own.
        """
        try:
            db_connection, minio_connection, s3_connection, credentials = self._validate()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        s3_parameters = s3_connection
        if self.config["storage-type"] == StorageType.minio:
            s3_parameters = minio_connection

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

        if not self.ingress.url:
            logger.info("Ingress relation not configured; Airbyte is not exposed via ingress")

        # Runtime services crash without DATAPLANE_CLIENT_ID/SECRET, so until the secret exists
        # configure only the bootloader and leave the rest unconfigured; update-status then
        # re-reconciles once it appears.
        dataplane_env = self._get_auth_secret_env()

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            container = self.unit.get_container(container_name)
            if not container.can_connect():
                continue

            if not dataplane_env and container_name != "airbyte-bootloader":
                continue

            env = create_env(
                self.model.name,
                self.app.name,
                container_name,
                self.config,
                db_connection=db_connection,
                minio_connection=minio_connection,
                s3_connection=s3_connection,
                credentials=credentials,
            )
            env = {k: v for k, v in env.items() if v is not None}
            env.update(dataplane_env)

            pebble_layer = get_pebble_layer(container_name, env)
            container.add_layer(container_name, pebble_layer, combine=True)
            container.replan()

        if not dataplane_env:
            self.unit.status = WaitingStatus("waiting for airbyte-auth-secrets")
            return

        self.unit.status = MaintenanceStatus("replanning application")


if __name__ == "__main__":  # pragma: nocover
    ops.main(AirbyteK8SOperatorCharm)
