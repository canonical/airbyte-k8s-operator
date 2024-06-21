# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing


"""Charm unit tests."""

# pylint:disable=protected-access,too-many-public-methods

import logging
from unittest import TestCase, mock

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import CheckStatus
from ops.testing import Harness

from charm import AirbyteK8SOperatorCharm
from src.literals import BASE_ENV, CONTAINERS
from src.structured_config import StorageType

logging.basicConfig(level=logging.DEBUG)

mock_incomplete_pebble_plan = {"services": {"airbyte": {"override": "replace"}}}

MODEL_NAME = "airbyte-model"
APP_NAME = "airbyte-k8s"

minio_object_storage_data = {
    "access-key": "access",
    "secret-key": "secret",
    "service": "service",
    "port": "9000",
    "namespace": "namespace",
    "secure": False,
    "endpoint": "endpoint",
}


class TestCharm(TestCase):
    """Unit tests.

    Attrs:
        maxDiff: Specifies max difference shown by failed tests.
    """

    maxDiff = None

    def setUp(self):
        """Set up for the unit tests."""
        self.harness = Harness(AirbyteK8SOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        for container_name in list(CONTAINERS.keys()):
            self.harness.set_can_connect(container_name, True)
        self.harness.set_leader(True)
        self.harness.set_model_name("airbyte-model")
        self.harness.add_network("10.0.0.10", endpoint="peer")
        self.harness.begin()

    def test_initial_plan(self):
        """The initial pebble plan is empty."""
        harness = self.harness
        for container_name in list(CONTAINERS.keys()):
            initial_plan = harness.get_container_pebble_plan(container_name).to_dict()
            self.assertEqual(initial_plan, {})

    def test_blocked_by_peer_relation_not_ready(self):
        """The charm is blocked without a peer relation."""
        harness = self.harness

        simulate_pebble_readiness(harness)

        # The BlockStatus is set with a message.
        self.assertEqual(harness.model.unit.status, BlockedStatus("peer relation not ready"))

    def test_blocked_by_db(self):
        """The charm is blocked without a db:pgsql relation with a ready master."""
        harness = self.harness

        # Simulate peer relation readiness.
        harness.add_relation("peer", "airbyte")

        simulate_pebble_readiness(harness)

        # The BlockStatus is set with a message.
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("database relation not ready"),
        )

    def test_blocked_by_minio(self):
        """The charm is blocked without a minio relation."""
        harness = self.harness

        # Simulate peer relation readiness.
        harness.add_relation("peer", "airbyte")

        simulate_pebble_readiness(harness)

        # Simulate db readiness.
        event = make_database_changed_event("db")
        harness.charm.postgresql._on_database_changed(event)

        # The BlockStatus is set with a message.
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("minio relation not ready"),
        )

    def test_blocked_by_s3(self):
        """The charm is blocked without a minio relation."""
        harness = self.harness

        harness.update_config({"storage-type": "S3"})

        # Simulate peer relation readiness.
        harness.add_relation("peer", "airbyte")

        simulate_pebble_readiness(harness)

        # Simulate db readiness.
        event = make_database_changed_event("db")
        harness.charm.postgresql._on_database_changed(event)

        # The BlockStatus is set with a message.
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("s3 relation not ready"),
        )

    def test_ready_with_minio(self):
        """The pebble plan is correctly generated when the charm is ready."""
        harness = self.harness
        harness.update_config({"storage-type": "MINIO"})

        simulate_lifecycle(harness)

        # The plan is generated after pebble is ready.
        for container_name in list(CONTAINERS.keys()):
            want_plan = create_plan(container_name, "MINIO")

            got_plan = harness.get_container_pebble_plan(container_name).to_dict()
            self.assertEqual(got_plan, want_plan)

            # The service was started.
            service = harness.model.unit.get_container(container_name).get_service(container_name)
            self.assertTrue(service.is_running())

        self.assertEqual(harness.model.unit.status, MaintenanceStatus("replanning application"))

    def test_ready_with_s3(self):
        """The pebble plan is correctly generated when the charm is ready."""
        harness = self.harness
        harness.update_config({"storage-type": "S3"})

        simulate_lifecycle(harness)

        # The plan is generated after pebble is ready.
        for container_name in list(CONTAINERS.keys()):
            want_plan = create_plan(container_name, "S3")

            got_plan = harness.get_container_pebble_plan(container_name).to_dict()
            self.assertEqual(got_plan, want_plan)

            # The service was started.
            service = harness.model.unit.get_container(container_name).get_service(container_name)
            self.assertTrue(service.is_running())

        self.assertEqual(harness.model.unit.status, MaintenanceStatus("replanning application"))

    def test_update_status_up(self):
        """The charm updates the unit status to active based on UP status."""
        harness = self.harness

        simulate_lifecycle(harness)
        for container_name in list(CONTAINERS.keys()):
            container = harness.model.unit.get_container(container_name)
            if CONTAINERS[container_name]:
                container.get_check = mock.Mock(status="up")
                container.get_check.return_value.status = CheckStatus.UP

        harness.charm.on.update_status.emit()
        self.assertEqual(harness.model.unit.status, ActiveStatus())

    def test_update_status_down(self):
        """The charm updates the unit status to maintenance based on DOWN status."""
        harness = self.harness

        simulate_lifecycle(harness)

        for container_name in list(CONTAINERS.keys()):
            container = harness.model.unit.get_container(container_name)
            if CONTAINERS[container_name]:
                container.get_check = mock.Mock(status="up")
                container.get_check.return_value.status = CheckStatus.DOWN

        harness.charm.on.update_status.emit()
        self.assertEqual(harness.model.unit.status, MaintenanceStatus("Status check: DOWN"))

    def test_incomplete_pebble_plan(self):
        """The charm re-applies the pebble plan if incomplete."""
        harness = self.harness
        simulate_lifecycle(harness)

        for container_name in list(CONTAINERS.keys()):
            container = harness.model.unit.get_container(container_name)
            container.add_layer(container_name, mock_incomplete_pebble_plan, combine=True)
            if CONTAINERS[container_name]:
                container.get_check = mock.Mock(status="up")
                container.get_check.return_value.status = CheckStatus.UP

        harness.charm.on.update_status.emit()

        self.assertEqual(
            harness.model.unit.status,
            ActiveStatus(),
        )
        plan = harness.get_container_pebble_plan("airbyte-server").to_dict()
        assert plan != mock_incomplete_pebble_plan

    @mock.patch("charm.AirbyteK8SOperatorCharm._validate_pebble_plan", return_value=True)
    @mock.patch("s3_helpers.S3Client.create_bucket_if_not_exists", return_value=None)
    @mock.patch("s3_helpers.S3Client.set_bucket_lifecycle_policy", return_value=None)
    def test_missing_pebble_plan(
        self, set_bucket_lifecycle_policy, create_bucket_if_not_exists, mock_validate_pebble_plan
    ):
        """The charm re-applies the pebble plan if missing."""
        harness = self.harness
        simulate_lifecycle(harness)

        mock_validate_pebble_plan.return_value = False
        harness.charm.on.update_status.emit()
        self.assertEqual(
            harness.model.unit.status,
            MaintenanceStatus("replanning application"),
        )
        plan = harness.get_container_pebble_plan("airbyte-server").to_dict()
        assert plan is not None


@mock.patch("s3_helpers.S3Client.create_bucket_if_not_exists", return_value=None)
@mock.patch("s3_helpers.S3Client.set_bucket_lifecycle_policy", return_value=None)
@mock.patch(
    "relations.minio.MinioRelation._get_object_storage_data",
    return_value=minio_object_storage_data,
)
@mock.patch("relations.minio.MinioRelation._get_interfaces", return_value=None)
def simulate_lifecycle(
    harness,
    _get_interfaces,
    _get_object_storage_data,
    create_bucket_if_not_exists,
    set_bucket_lifecycle_policy,
):
    """Simulate a healthy charm life-cycle.

    Args:
        harness: ops.testing.Harness object used to simulate charm lifecycle.
    """
    # Simulate peer relation readiness.
    harness.add_relation("peer", "airbyte")

    simulate_pebble_readiness(harness)

    # Simulate db readiness.
    event = make_database_changed_event("db")
    harness.charm.postgresql._on_database_changed(event)

    # Simulate minio relation
    harness.add_relation("object-storage", "airbyte")
    harness.charm.minio._on_object_storage_relation_changed(None)

    # Simulate s3 relation
    relation_id = harness.add_relation("s3-parameters", "airbyte")
    harness.update_relation_data(
        relation_id,
        "airbyte",
        s3_provider_databag(),
    )


def simulate_pebble_readiness(harness):
    # Simulate pebble readiness on all containers.
    for container_name in list(CONTAINERS.keys()):
        container = harness.model.unit.get_container(container_name)
        harness.charm.on[container_name].pebble_ready.emit(container)


def make_database_changed_event(rel_name):
    """Create and return a mock master changed event.

    The event is generated by the relation with the given name.

    Args:
        rel_name: Name of the database relation (db or visibility)

    Returns:
        Event dict.
    """
    return type(
        "Event",
        (),
        {
            "endpoints": "myhost:5432,anotherhost:2345",
            "username": f"jean-luc@{rel_name}",
            "password": "inner-light",
            "relation": type("Relation", (), {"name": rel_name}),
        },
    )


def s3_provider_databag():
    """Create and return mock s3 credentials.

    Returns:
        S3 parameters.
    """
    return {
        "access-key": "access",
        "secret-key": "secret",
        "bucket": "bucket_name",
        "endpoint": "http://endpoint",
        "path": "path",
        "region": "region",
        "s3-uri-style": "path",
    }


def create_plan(container_name, storage_type):
    want_plan = {
        "services": {
            container_name: {
                "summary": container_name,
                "command": f"/bin/bash -c airbyte-app/bin/{container_name}",
                "startup": "enabled",
                "override": "replace",
                "environment": {
                    **BASE_ENV,
                    "AIRBYTE_API_HOST": "airbyte-k8s:8006/api/public",
                    "AIRBYTE_SERVER_HOST": "airbyte-k8s:8001",
                    "AIRBYTE_URL": "http://airbyte-ui-k8s:8080",
                    "AWS_ACCESS_KEY_ID": "access",
                    "AWS_SECRET_ACCESS_KEY": "secret",
                    "CONFIG_API_HOST": "airbyte-k8s:8001",
                    "CONNECTOR_BUILDER_API_HOST": "airbyte-k8s:80",
                    "CONNECTOR_BUILDER_API_URL": "/connector-builder-api",
                    "CONNECTOR_BUILDER_SERVER_API_HOST": "airbyte-k8s:80",
                    "DATABASE_DB": "airbyte-k8s_db",
                    "DATABASE_HOST": "myhost",
                    "DATABASE_PASSWORD": "inner-light",
                    "DATABASE_PORT": "5432",
                    "DATABASE_URL": "jdbc:postgresql://myhost:5432/airbyte-k8s_db",
                    "DATABASE_USER": "jean-luc@db",
                    "INTERNAL_API_HOST": "airbyte-k8s:8001",
                    "JOBS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.29.15.001",
                    "JOB_KUBE_MAIN_CONTAINER_IMAGE_PULL_POLICY": "IfNotPresent",
                    "JOB_KUBE_NAMESPACE": "airbyte-model",
                    "JOB_KUBE_SERVICEACCOUNT": "airbyte-k8s",
                    "JOB_KUBE_SIDECAR_CONTAINER_IMAGE_PULL_POLICY": "IfNotPresent",
                    "KEYCLOAK_DATABASE_URL": "jdbc:postgresql://myhost:5432/airbyte-k8s_db?currentSchema=keycloak",
                    "KEYCLOAK_INTERNAL_HOST": "localhost",
                    "LOG_LEVEL": "INFO",
                    "MAX_CHECK_WORKERS": 5,
                    "MAX_DISCOVER_WORKERS": 5,
                    "MAX_SPEC_WORKERS": 5,
                    "MAX_SYNC_WORKERS": 5,
                    "RUNNING_TTL_MINUTES": 240,
                    "S3_LOG_BUCKET": "airbyte-dev-logs",
                    "SHOULD_RUN_NOTIFY_WORKFLOWS": "true",
                    "STORAGE_BUCKET_ACTIVITY_PAYLOAD": "airbyte-payload-storage",
                    "STORAGE_BUCKET_LOG": "airbyte-dev-logs",
                    "STORAGE_BUCKET_STATE": "airbyte-state-storage",
                    "STORAGE_BUCKET_WORKLOAD_OUTPUT": "airbyte-state-storage",
                    "STORAGE_TYPE": storage_type,
                    "SUCCEEDED_TTL_MINUTES": 30,
                    "SYNC_JOB_RETRIES_COMPLETE_FAILURES_BACKOFF_BASE": 3,
                    "SYNC_JOB_RETRIES_COMPLETE_FAILURES_BACKOFF_MAX_INTERVAL_S": 1800,
                    "SYNC_JOB_RETRIES_COMPLETE_FAILURES_BACKOFF_MIN_INTERVAL_S": 10,
                    "SYNC_JOB_RETRIES_COMPLETE_FAILURES_MAX_SUCCESSIVE": 5,
                    "SYNC_JOB_RETRIES_COMPLETE_FAILURES_MAX_TOTAL": 10,
                    "SYNC_JOB_RETRIES_PARTIAL_FAILURES_MAX_SUCCESSIVE": 1000,
                    "SYNC_JOB_RETRIES_PARTIAL_FAILURES_MAX_TOTAL": 20,
                    "TEMPORAL_HISTORY_RETENTION_IN_DAYS": 30,
                    "TEMPORAL_HOST": "temporal-k8s:7233",
                    "TEMPORAL_WORKER_PORTS": "9001,9002,9003,9004,9005,9006,9007,9008,9009,9010,9011,9012,9013,9014,9015,9016,9017,9018,9019,9020,9021,9022,9023,9024,9025,9026,9027,9028,9029,9030",
                    "UNSUCCESSFUL_TTL_MINUTES": 1440,
                    "VAULT_AUTH_METHOD": "token",
                    "WEBAPP_URL": "http://airbyte-ui-k8s:8080",
                    "WORKER_LOGS_STORAGE_TYPE": storage_type,
                    "WORKER_STATE_STORAGE_TYPE": storage_type,
                    "WORKLOAD_API_HOST": "localhost",
                },
            },
        },
    }

    if container_name == "airbyte-api-server":
        want_plan["services"][container_name]["environment"].update({"INTERNAL_API_HOST": f"http://airbyte-k8s:8001"})

    if storage_type == StorageType.minio:
        want_plan["services"][container_name]["environment"].update(
            {
                "MINIO_ENDPOINT": "http://service.namespace.svc.cluster.local:9000",
                "AWS_ACCESS_KEY_ID": "access",
                "AWS_SECRET_ACCESS_KEY": "secret",
                "STATE_STORAGE_MINIO_ENDPOINT": "http://service.namespace.svc.cluster.local:9000",
                "STATE_STORAGE_MINIO_ACCESS_KEY": "access",
                "STATE_STORAGE_MINIO_SECRET_ACCESS_KEY": "secret",
                "STATE_STORAGE_MINIO_BUCKET_NAME": "airbyte-state-storage",
                "S3_PATH_STYLE_ACCESS": "true",
            }
        )

    if storage_type == StorageType.s3:
        want_plan["services"][container_name]["environment"].update(
            {
                "AWS_ACCESS_KEY_ID": "access",
                "AWS_SECRET_ACCESS_KEY": "secret",
                "S3_LOG_BUCKET_REGION": "region",
                "AWS_DEFAULT_REGION": "region",
            }
        )

    application_info = CONTAINERS[container_name]
    if application_info:
        want_plan["services"][container_name].update(
            {
                "on-check-failure": {"up": "ignore"},
            }
        )
        want_plan.update(
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

    return want_plan
