# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm literals."""

CONNECTOR_BUILDER_SERVER_API_PORT = 80
INTERNAL_API_PORT = 8001
AIRBYTE_API_PORT = 8006
WORKLOAD_API_PORT = 8007
AIRBYTE_VERSION = "0.63.8"
DB_NAME = "airbyte-k8s_db"


CONTAINER_HEALTH_CHECK_MAP = {
    "airbyte-api-server": {
        "port": AIRBYTE_API_PORT,
        "health_endpoint": "/health",
    },
    "airbyte-bootloader": None,
    "airbyte-connector-builder-server": None,
    "airbyte-cron": {
        "port": 9001,
        "health_endpoint": "/health",
    },
    "airbyte-pod-sweeper": None,
    "airbyte-server": {
        "port": INTERNAL_API_PORT,
        "health_endpoint": "/api/v1/health",
    },
    "airbyte-workers": {"port": 9000, "health_endpoint": "/"},
}

REQUIRED_S3_PARAMETERS = ["region", "endpoint", "access-key", "secret-key"]
BUCKET_CONFIGS = [
    "storage-bucket-logs",
    "storage-bucket-state",
    "storage-bucket-activity-payload",
    "storage-bucket-workload-output",
]
LOGS_BUCKET_CONFIG = "storage-bucket-logs"

BASE_ENV = {
    "API_URL": "/api/v1/",
    "AIRBYTE_VERSION": AIRBYTE_VERSION,
    "AIRBYTE_EDITION": "community",
    "AUTO_DETECT_SCHEMA": "true",
    "WORKSPACE_ROOT": "/workspace",
    "CONFIG_ROOT": "/configs",
    "CONFIGS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.35.15.001",
    "JOBS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.29.15.001",
    "MICRONAUT_ENVIRONMENTS": "control-plane",
    "WORKERS_MICRONAUT_ENVIRONMENTS": "control-plane",
    "CRON_MICRONAUT_ENVIRONMENTS": "control-plane",
    "WORKLOAD_API_HOST": "localhost",
    "MICROMETER_METRICS_ENABLED": "false",
    "LAUNCHER_MICRONAUT_ENVIRONMENTS": "control-plane,oss",
    "KEYCLOAK_INTERNAL_HOST": "localhost",
    "WORKER_ENVIRONMENT": "kubernetes",
    "SHOULD_RUN_NOTIFY_WORKFLOWS": "true",
    "CONNECTOR_BUILDER_API_URL": "/connector-builder-api",
    "TEMPORAL_WORKER_PORTS": "9001,9002,9003,9004,9005,9006,9007,9008,9009,9010,9011,9012,9013,9014,9015,9016,9017,9018,9019,9020,9021,9022,9023,9024,9025,9026,9027,9028,9029,9030",
    "CONTAINER_ORCHESTRATOR_ENABLED": "true",
    "CONTAINER_ORCHESTRATOR_IMAGE": f"airbyte/container-orchestrator:{AIRBYTE_VERSION}",
    "LOG4J_CONFIGURATION_FILE": "log4j2-minio.xml",
}
