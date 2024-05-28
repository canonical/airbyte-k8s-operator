# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Literals."""

# TODO (kelkawi-a): perform up check on the following ports for each container
CONTAINERS = {
    "airbyte-api-server": 8006,
    "airbyte-bootloader": None,
    "airbyte-connector-builder-server": 8080,
    "airbyte-cron": 9001,
    "airbyte-pod-sweeper": None,
    "airbyte-server": 8001,
    "airbyte-workers": 9000,
}

DB_NAME = "airbyte-k8s_db"
CONNECTOR_BUILDER_SERVER_API_PORT = 80
INTERNAL_API_PORT = 8001
AIRBYTE_API_PORT = 8006
WORKLOAD_API_PORT = 8007
REQUIRED_MINIO_CONFIG = ["minio-host", "minio-access-key", "minio-secret-key"]
REQUIRED_S3_PARAMETERS = ["region", "endpoint", "access-key", "secret-key"]
AIRBYTE_VERSION = "0.57.3"
BUCKET_CONFIGS = [
    "storage-bucket-logs",
    "storage-bucket-state",
    "storage-bucket-activity-payload",
    "storage-bucket-workload-output",
]
LOGS_BUCKET_CONFIG = "storage-bucket-logs"
