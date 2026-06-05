# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing


"""Charm unit tests."""

# pylint:disable=protected-access,too-many-public-methods

import base64
import dataclasses
import json
import logging
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import CheckLevel, CheckStartup, CheckStatus, Layer

from charm import AirbyteK8SOperatorCharm
from src.literals import BASE_ENV, CONTAINER_HEALTH_CHECK_MAP
from src.structured_config import StorageType

logging.basicConfig(level=logging.DEBUG)

mock_incomplete_pebble_plan = {"services": {"airbyte": {"override": "replace"}}}

MODEL_NAME = "airbyte-model"
APP_NAME = "airbyte-k8s"

# The charm persists relation data in the `airbyte-peer` databag via the `State`
# class, so a "ready" charm is reproduced by pre-populating that databag rather
# than by replaying the db/minio/s3 relation events.
DB_CONNECTION = {
    "dbname": "airbyte-k8s_db",
    "host": "myhost",
    "port": "5432",
    "password": "inner-light",  # nosec
    "user": "jean-luc@db",
}
MINIO_STATE = {
    "access-key": "access",
    "secret-key": "secret",
    "service": "service",
    "port": "9000",
    "namespace": "namespace",
    "secure": False,
    "endpoint": "http://service.namespace.svc.cluster.local:9000",
}
S3_STATE = {
    "bucket": "bucket_name",
    "endpoint": "http://endpoint",
    "region": "region",
    "access-key": "access",
    "secret-key": "secret",
    "uri_style": "path",
}

# Raw object-storage data as returned by the minio interface, before the charm
# derives the service endpoint from it.
MINIO_RAW = {
    "access-key": "access",
    "secret-key": "secret",
    "service": "service",
    "port": "9000",
    "namespace": "namespace",
    "secure": False,
}


class TestCharm(TestCase):
    """Unit tests.

    Attrs:
        maxDiff: Specifies max difference shown by failed tests.
    """

    maxDiff = None

    def setUp(self):
        """Set up for the unit tests."""
        patcher1 = patch("kubernetes.config.load_incluster_config")
        patcher2 = patch("kubernetes.client.CoreV1Api")
        self.mock_incluster_config = patcher1.start()
        self.mock_k8s_api = patcher2.start()
        self.addCleanup(patcher1.stop)
        self.addCleanup(patcher2.stop)
        self.mock_core_v1_instance = MagicMock()
        self.mock_k8s_api.return_value = self.mock_core_v1_instance

        fake_secret = MagicMock()
        fake_secret.data = {
            "dataplane-client-id": base64.b64encode(b"sample-client-id"),
            "dataplane-client-secret": base64.b64encode(b"sample-client-secret"),
        }
        self.mock_core_v1_instance.read_namespaced_secret.return_value = fake_secret

        # The S3/MinIO client only performs bucket operations during `_update`;
        # stubbed out so no object storage is contacted.
        for target in (
            "s3_helpers.S3Client.create_bucket_if_not_exists",
            "s3_helpers.S3Client.set_bucket_lifecycle_policy",
        ):
            stub = patch(target, return_value=None)
            stub.start()
            self.addCleanup(stub.stop)

        self.ctx = testing.Context(AirbyteK8SOperatorCharm)

    def test_initial_plan(self):
        """The pebble plan is empty before the charm is ready."""
        state = make_state(peer=False)
        out = self.ctx.run(self.ctx.on.update_status(), state)
        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            self.assertEqual(out.get_container(container_name).plan.to_dict(), {})

    def test_blocked_by_peer_relation_not_ready(self):
        """The charm is blocked without a peer relation."""
        state = make_state(peer=False)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)
        self.assertEqual(out.unit_status, BlockedStatus("peer relation not ready"))

    def test_blocked_by_db(self):
        """The charm is blocked without a db:pgsql relation with a ready master."""
        state = make_state()
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)
        self.assertEqual(out.unit_status, BlockedStatus("database relation not ready"))

    def test_blocked_by_minio(self):
        """The charm is blocked without a minio relation."""
        state = make_state(db=True)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)
        self.assertEqual(out.unit_status, BlockedStatus("minio relation not ready"))

    def test_blocked_by_s3(self):
        """The charm is blocked without an s3 relation."""
        state = make_state(config={"storage-type": "S3"}, db=True)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)
        self.assertEqual(out.unit_status, BlockedStatus("s3 relation not ready"))

    def test_ready_with_minio(self):
        """The pebble plan is correctly generated when the charm is ready."""
        state = make_state(config={"storage-type": "MINIO"}, db=True, minio=True)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            got_plan = out.get_container(container_name).plan.to_dict()
            self.assertEqual(got_plan, create_plan(container_name, "MINIO"))

        self.assertEqual(out.unit_status, MaintenanceStatus("replanning application"))

    def test_ready_with_s3(self):
        """The pebble plan is correctly generated when the charm is ready."""
        state = make_state(config={"storage-type": "S3"}, db=True, s3=True)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            got_plan = out.get_container(container_name).plan.to_dict()
            self.assertEqual(got_plan, create_plan(container_name, "S3"))

        self.assertEqual(out.unit_status, MaintenanceStatus("replanning application"))

    def test_update_status_up(self):
        """The charm updates the unit status to active based on UP status."""
        state = make_state(db=True, minio=True)
        mid = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        mid = with_checks(mid, CheckStatus.UP)
        out = self.ctx.run(self.ctx.on.update_status(), mid)
        self.assertEqual(out.unit_status, ActiveStatus())

    def test_update_status_down(self):
        """The charm updates the unit status to maintenance based on DOWN status."""
        state = make_state(db=True, minio=True)
        mid = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        mid = with_checks(mid, CheckStatus.DOWN)
        out = self.ctx.run(self.ctx.on.update_status(), mid)
        self.assertEqual(out.unit_status, MaintenanceStatus("Status check: 'airbyte-workload-api-server' DOWN"))

    def test_incomplete_pebble_plan(self):
        """The charm re-applies the pebble plan if incomplete."""
        state = make_state(db=True, minio=True)
        mid = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        containers = set()
        for container in mid.containers:
            layers = {**container.layers, "incomplete": Layer(mock_incomplete_pebble_plan)}
            containers.add(dataclasses.replace(container, layers=layers))
        mid = with_checks(dataclasses.replace(mid, containers=containers), CheckStatus.UP)

        out = self.ctx.run(self.ctx.on.update_status(), mid)
        self.assertEqual(out.unit_status, ActiveStatus())
        plan = out.get_container("airbyte-server").plan.to_dict()
        self.assertNotEqual(plan, mock_incomplete_pebble_plan)

    def test_missing_pebble_plan(self):
        """The charm re-applies the pebble plan if missing."""
        state = make_state(db=True, minio=True)
        with patch("charm.AirbyteK8SOperatorCharm._validate_pebble_plan", return_value=False):
            out = self.ctx.run(self.ctx.on.update_status(), state)

        self.assertEqual(out.unit_status, MaintenanceStatus("replanning application"))
        plan = out.get_container("airbyte-server").plan.to_dict()
        self.assertIsNotNone(plan)

    def test_feature_flags_heartbeat_only(self):
        """The charm generates flags file and sets env vars when heartbeat config is set."""
        state = make_state(config={"heartbeat-max-seconds-between-messages": 3600}, db=True, minio=True)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        for container_name in CONTAINER_HEALTH_CHECK_MAP:
            container = out.get_container(container_name)
            flags_file = container.get_filesystem(self.ctx) / "flags"
            self.assertTrue(flags_file.exists())

            flags_content = flags_file.read_text()
            self.assertIn("heartbeat-max-seconds-between-messages", flags_content)
            self.assertIn('serve: "3600"', flags_content)

            env = container.plan.to_dict()["services"][container_name]["environment"]
            self.assertEqual(env["FEATURE_FLAG_PATH"], "/flags")
            self.assertEqual(env["FEATURE_FLAG_CLIENT"], "configfile")
            self.assertIn("FEATURE_FLAG_HASH", env)

    def test_feature_flags_destination_timeout(self):
        """The charm generates flags file with destination timeout settings."""
        state = make_state(
            config={"destination-timeout-max-seconds": 86400, "destination-timeout-fail-sync": True},
            db=True,
            minio=True,
        )
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        flags_content = (out.get_container("airbyte-server").get_filesystem(self.ctx) / "flags").read_text()
        self.assertIn("destination-timeout-enabled", flags_content)
        self.assertIn("serve: true", flags_content)
        self.assertIn("destination-timeout.seconds", flags_content)
        self.assertIn('serve: "86400"', flags_content)
        self.assertIn("destination-timeout.failSync", flags_content)

    def test_feature_flags_all_configs(self):
        """The charm generates flags file with all feature flag configs set."""
        state = make_state(
            config={
                "heartbeat-max-seconds-between-messages": 1800,
                "heartbeat-fail-sync": False,
                "destination-timeout-max-seconds": 43200,
                "destination-timeout-fail-sync": True,
            },
            db=True,
            minio=True,
        )
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        flags_content = (out.get_container("airbyte-workers").get_filesystem(self.ctx) / "flags").read_text()
        self.assertIn("heartbeat-max-seconds-between-messages", flags_content)
        self.assertIn('serve: "1800"', flags_content)
        self.assertIn("heartbeat.failSync", flags_content)
        self.assertIn("serve: false", flags_content)
        self.assertIn("destination-timeout-enabled", flags_content)
        self.assertIn("destination-timeout.seconds", flags_content)
        self.assertIn('serve: "43200"', flags_content)
        self.assertIn("destination-timeout.failSync", flags_content)

    def test_no_feature_flags_when_unset(self):
        """The charm does not set flag env vars when no flags are configured."""
        state = make_state(db=True, minio=True)
        out = self.ctx.run(self.ctx.on.pebble_ready(get_container(state, "airbyte-server")), state)

        container = out.get_container("airbyte-server")
        self.assertFalse((container.get_filesystem(self.ctx) / "flags").exists())

        env = container.plan.to_dict()["services"]["airbyte-server"]["environment"]
        self.assertNotIn("FEATURE_FLAG_PATH", env)
        self.assertNotIn("FEATURE_FLAG_CLIENT", env)
        self.assertNotIn("FEATURE_FLAG_HASH", env)

    def test_database_relation_changed(self):
        """The database relation handler stores the connection and replans."""
        db_relation = testing.Relation(
            "db",
            remote_app_data={
                "username": "jean-luc@db",
                "password": "inner-light",  # nosec
                "endpoints": "myhost:5432,anotherhost:2345",
                "database": "airbyte-k8s_db",
            },
        )
        state = add_relations(make_state(minio=True), db_relation)
        out = self.ctx.run(self.ctx.on.relation_changed(db_relation), state)

        self.assertEqual(json.loads(peer_data(out)["database_connection"]), DB_CONNECTION)
        self.assertEqual(out.unit_status, MaintenanceStatus("replanning application"))

    def test_database_relation_broken(self):
        """The database relation broken handler clears the stored connection."""
        db_relation = testing.Relation("db")
        state = add_relations(make_state(db=True, minio=True), db_relation)
        out = self.ctx.run(self.ctx.on.relation_broken(db_relation), state)

        self.assertEqual(json.loads(peer_data(out)["database_connection"]), None)

    def test_object_storage_relation_changed(self):
        """The minio relation handler stores object-storage data and replans."""
        obj_relation = testing.Relation("object-storage")
        state = add_relations(make_state(db=True), obj_relation)
        with patch("relations.minio.MinioRelation._get_interfaces", return_value=None), patch(
            "relations.minio.MinioRelation._get_object_storage_data", return_value=dict(MINIO_RAW)
        ):
            out = self.ctx.run(self.ctx.on.relation_changed(obj_relation), state)

        self.assertEqual(json.loads(peer_data(out)["minio"]), MINIO_STATE)
        self.assertEqual(out.unit_status, MaintenanceStatus("replanning application"))

    def test_s3_credentials_changed(self):
        """The s3 relation handler stores s3 parameters and replans."""
        s3_relation = testing.Relation("s3-parameters", remote_app_data=s3_provider_databag())
        state = add_relations(make_state(config={"storage-type": "S3"}, db=True), s3_relation)
        out = self.ctx.run(self.ctx.on.relation_changed(s3_relation), state)

        self.assertEqual(json.loads(peer_data(out)["s3"]), S3_STATE)
        self.assertEqual(out.unit_status, MaintenanceStatus("replanning application"))


def _up_check(status):
    """Build the "up" CheckInfo mirroring the charm's pebble check definition.

    The charm's layer defines the check without a level, startup or threshold, so
    those must be left unset here to keep the scenario consistent with the plan.

    Args:
        status: the ops.pebble.CheckStatus to report for the check.

    Returns:
        A testing.CheckInfo for the "up" check.
    """
    return testing.CheckInfo(
        "up",
        level=CheckLevel.UNSET,
        startup=CheckStartup.UNSET,
        threshold=None,
        status=status,
    )


def make_containers(check_status=None):
    """Build the set of charm containers.

    Args:
        check_status: optional ops.pebble.CheckStatus to attach as the "up" check
            for containers that define a health check.

    Returns:
        A set of testing.Container objects, all set to allow connection.
    """
    containers = set()
    for container_name, settings in CONTAINER_HEALTH_CHECK_MAP.items():
        check_infos = frozenset()
        if check_status is not None and settings:
            check_infos = frozenset({_up_check(check_status)})
        containers.add(testing.Container(container_name, can_connect=True, check_infos=check_infos))
    return containers


def make_state(*, config=None, leader=True, peer=True, db=False, minio=False, s3=False, containers=None):
    """Build a scenario State for the charm.

    Args:
        config: optional charm config overrides.
        leader: whether the unit is the leader.
        peer: whether the airbyte-peer relation is present.
        db: whether to mark the database connection as ready in the peer databag.
        minio: whether to mark the minio data as ready in the peer databag.
        s3: whether to mark the s3 data as ready in the peer databag.
        containers: optional explicit set of containers to use.

    Returns:
        A testing.State object.
    """
    relations = []
    if peer:
        local_app_data = {}
        if db:
            local_app_data["database_connection"] = json.dumps(DB_CONNECTION)
        if minio:
            local_app_data["minio"] = json.dumps(MINIO_STATE)
        if s3:
            local_app_data["s3"] = json.dumps(S3_STATE)
        relations.append(testing.PeerRelation("airbyte-peer", local_app_data=local_app_data))

    return testing.State(
        leader=leader,
        config=config or {},
        model=testing.Model(name=MODEL_NAME),
        relations=relations,
        containers=containers if containers is not None else make_containers(),
    )


def add_relations(state, *relations):
    """Return a copy of the state with extra relations added.

    Args:
        state: the testing.State to copy.
        relations: relations to add to the state.

    Returns:
        A new testing.State including the given relations.
    """
    return dataclasses.replace(state, relations=set(state.relations) | set(relations))


def peer_data(state):
    """Return the local app databag of the airbyte-peer relation.

    Args:
        state: the testing.State to read from.

    Returns:
        The peer relation's local app data mapping.
    """
    peer = next(relation for relation in state.relations if relation.endpoint == "airbyte-peer")
    return peer.local_app_data


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


def get_container(state, name):
    """Return the container with the given name from a state.

    Args:
        state: the testing.State to look in.
        name: the container name.

    Returns:
        The matching testing.Container.
    """
    return next(container for container in state.containers if container.name == name)


def with_checks(state, status):
    """Return a copy of the state with the "up" check set on health-checked containers.

    Args:
        state: the testing.State to copy.
        status: the ops.pebble.CheckStatus to apply.

    Returns:
        A new testing.State with updated container check info.
    """
    containers = set()
    for container in state.containers:
        if CONTAINER_HEALTH_CHECK_MAP[container.name]:
            container = dataclasses.replace(container, check_infos=frozenset({_up_check(status)}))
        containers.add(container)
    return dataclasses.replace(state, containers=containers)


def create_plan(container_name, storage_type):
    """Create container pebble plan.

    Args:
        container_name: Name of Airbyte container.
        storage_type: Type of storage in charm config.

    Returns:
        Container pebble plan.
    """
    want_plan = {
        "services": {
            container_name: {
                "summary": container_name,
                "command": f"/bin/bash {container_name}/airbyte-app/bin/{container_name}",
                "startup": "enabled",
                "override": "replace",
                "environment": {
                    **BASE_ENV,
                    "AIRBYTE_API_HOST": "airbyte-k8s:8006/api/public",
                    "AIRBYTE_SERVER_HOST": "airbyte-k8s:8001",
                    "AWS_ACCESS_KEY_ID": "access",  # nosec
                    "AWS_SECRET_ACCESS_KEY": "secret",  # nosec
                    "CONFIG_API_HOST": "airbyte-k8s:8001",
                    "CONTROL_PLANE_TOKEN_ENDPOINT": "http://airbyte-k8s:8001/api/v1/dataplanes/token",
                    "CONNECTOR_BUILDER_API_HOST": "airbyte-k8s:80",
                    "CONNECTOR_BUILDER_API_URL": "/connector-builder-api",
                    "CONNECTOR_BUILDER_SERVER_API_HOST": "airbyte-k8s:80",
                    "DATABASE_DB": "airbyte-k8s_db",
                    "DATABASE_HOST": "myhost",
                    "DATABASE_PASSWORD": "inner-light",  # nosec
                    "DATABASE_PORT": "5432",
                    "DATABASE_URL": "jdbc:postgresql://myhost:5432/airbyte-k8s_db",
                    "DATABASE_USER": "jean-luc@db",
                    "DATAPLANE_CLIENT_ID": "sample-client-id",
                    "DATAPLANE_CLIENT_SECRET": "sample-client-secret",
                    "INTERNAL_API_HOST": "http://airbyte-k8s:8001",
                    "JOBS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.29.15.001",
                    "JOB_KUBE_MAIN_CONTAINER_IMAGE_PULL_POLICY": "IfNotPresent",
                    "JOB_KUBE_NAMESPACE": "airbyte-model",
                    "JOB_KUBE_SERVICEACCOUNT": "airbyte-k8s",
                    "JOB_KUBE_SIDECAR_CONTAINER_IMAGE_PULL_POLICY": "IfNotPresent",
                    "KEYCLOAK_DATABASE_URL": "jdbc:postgresql://myhost:5432/airbyte-k8s_db?currentSchema=keycloak",
                    "KEYCLOAK_INTERNAL_HOST": "localhost",
                    "LOG_LEVEL": "INFO",
                    "MAX_CHECK_WORKERS": 5,
                    "MAX_DAYS_OF_ONLY_FAILED_JOBS_BEFORE_CONNECTION_DISABLE": 14,
                    "MAX_DISCOVER_WORKERS": 5,
                    "MAX_FAILED_JOBS_IN_A_ROW_BEFORE_CONNECTION_DISABLE": 20,
                    "MAX_FIELDS_PER_CONNECTION": 20000,
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
                    "SYNC_JOB_MAX_TIMEOUT_DAYS": 3,
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
                    "WORKLOAD_API_HOST": "airbyte-k8s:8007",
                    "WORKLOAD_INIT_IMAGE": "airbyte/workload-init-container:1.7.0",
                    "WORKLOAD_API_BEARER_TOKEN": ".Values.workload-api.bearerToken",  # nosec
                },
            },
        },
    }

    if container_name == "airbyte-bootloader":
        want_plan["services"][container_name].update({"on-success": "ignore"})

    if container_name in ["airbyte-workload-launcher", "airbyte-workers", "airbyte-cron"]:
        want_plan["services"][container_name]["environment"].update(
            {"INTERNAL_API_HOST": "http://airbyte-k8s:8001", "WORKLOAD_API_HOST": "http://airbyte-k8s:8007"}
        )

    if storage_type == StorageType.minio:
        want_plan["services"][container_name]["environment"].update(
            {
                "MINIO_ENDPOINT": "http://service.namespace.svc.cluster.local:9000",
                "AWS_ACCESS_KEY_ID": "access",  # nosec
                "AWS_SECRET_ACCESS_KEY": "secret",  # nosec
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
                "AWS_ACCESS_KEY_ID": "access",  # nosec
                "AWS_SECRET_ACCESS_KEY": "secret",  # nosec
                "S3_LOG_BUCKET_REGION": "region",
                "AWS_DEFAULT_REGION": "region",
            }
        )

    application_info = CONTAINER_HEALTH_CHECK_MAP[container_name]
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
