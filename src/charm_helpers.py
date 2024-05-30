# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm helpers."""

import os
from urllib.parse import urlparse

from literals import (
    AIRBYTE_API_PORT,
    AIRBYTE_VERSION,
    CONNECTOR_BUILDER_SERVER_API_PORT,
    INTERNAL_API_PORT,
    WORKLOAD_API_PORT,
)
from structured_config import StorageType


def create_env(model_name, app_name, config, state):
    db_conn = state.database_connection

    host = db_conn["host"]
    port = db_conn["port"]
    db_name = db_conn["dbname"]
    db_url = f"jdbc:postgresql://{host}:{port}/{db_name}"

    env = {
        "API_URL": "/api/v1/",
        "AIRBYTE_VERSION": AIRBYTE_VERSION,
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
        "TEMPORAL_HOST": config["temporal-host"],
        "WORKER_LOGS_STORAGE_TYPE": config["storage-type"].value,
        "WORKER_STATE_STORAGE_TYPE": config["storage-type"].value,
        "STORAGE_TYPE": config["storage-type"].value,
        "STORAGE_BUCKET_LOG": config["storage-bucket-logs"],
        "S3_LOG_BUCKET": config["storage-bucket-logs"],
        "STORAGE_BUCKET_STATE": config["storage-bucket-state"],
        "STORAGE_BUCKET_WORKLOAD_OUTPUT": config["storage-bucket-workload-output"],
        "STORAGE_BUCKET_ACTIVITY_PAYLOAD": config["storage-bucket-activity-payload"],
        "CONFIGS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.40.23.002",
        "JOBS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION": "0.40.26.001",
        "MICRONAUT_ENVIRONMENTS": "control-plane",
        "WORKERS_MICRONAUT_ENVIRONMENTS": "control-plane",
        "CRON_MICRONAUT_ENVIRONMENTS": "control-plane",
        "INTERNAL_API_HOST": f"localhost:{INTERNAL_API_PORT}",
        "CONNECTOR_BUILDER_SERVER_API_HOST": f"localhost:{CONNECTOR_BUILDER_SERVER_API_PORT}",
        "AIRBYTE_API_HOST": f"localhost:{AIRBYTE_API_PORT}",
        "WORKLOAD_API_HOST": f"localhost:{WORKLOAD_API_PORT}",
        "WORKLOAD_API_URL": f"localhost:{WORKLOAD_API_PORT}",
        "LOG_LEVEL": config["log-level"].value,
        "MICROMETER_METRICS_ENABLED": "false",
        "LAUNCHER_MICRONAUT_ENVIRONMENTS": "control-plane,oss",
        "KEYCLOAK_INTERNAL_HOST": "localhost",
        "KEYCLOAK_DATABASE_URL": db_url + "?currentSchema=keycloak",
        "WEBAPP_URL": "airbyte-ui-k8s:8080",
        "WORKER_ENVIRONMENT": "kubernetes",
        "SECRET_PERSISTENCE": "TESTING_CONFIG_DB_TABLE",
        "SHOULD_RUN_NOTIFY_WORKFLOWS": "true",
        "CONNECTOR_BUILDER_API_URL": "/connector-builder-api",
        "TEMPORAL_WORKER_PORTS": "9001,9002,9003,9004,9005,9006,9007,9008,9009,9010,9011,9012,9013,9014,9015,9016,9017,9018,9019,9020,9021,9022,9023,9024,9025,9026,9027,9028,9029,9030",
        "JOB_KUBE_SERVICEACCOUNT": app_name,
        "JOB_KUBE_NAMESPACE": model_name,
        "RUNNING_TTL_MINUTES": config["pod-running-ttl-minutes"],
        "SUCCEEDED_TTL_MINUTES": config["pod-successful-ttl-minutes"],
        "UNSUCCESSFUL_TTL_MINUTES": config["pod-unsuccessful-ttl-minutes"],
    }

    if config["storage-type"].value == StorageType.minio and state.minio:
        minio_endpoint = construct_svc_endpoint(
            state.minio["service"],
            state.minio["namespace"],
            state.minio["port"],
            state.minio["secure"],
        )
        env.update(
            {
                "MINIO_ENDPOINT": minio_endpoint,
                "AWS_ACCESS_KEY_ID": state.minio["access-key"],
                "AWS_SECRET_ACCESS_KEY": state.minio["secret-key"],
                "STATE_STORAGE_MINIO_ENDPOINT": minio_endpoint,
                "STATE_STORAGE_MINIO_ACCESS_KEY": state.minio["access-key"],
                "STATE_STORAGE_MINIO_SECRET_ACCESS_KEY": state.minio["secret-key"],
                "STATE_STORAGE_MINIO_BUCKET_NAME": config["storage-bucket-state"],
                "S3_PATH_STYLE_ACCESS": "true",
            }
        )

    if config["storage-type"].value == StorageType.s3 and state.s3:
        env.update(
            {
                "AWS_ACCESS_KEY_ID": state.s3["access-key"],
                "AWS_SECRET_ACCESS_KEY": state.s3["secret-key"],
                "S3_LOG_BUCKET_REGION": state.s3["region"],
                "AWS_DEFAULT_REGION": state.s3["region"],
            }
        )

    http_proxy = os.environ.get("JUJU_CHARM_HTTP_PROXY")
    https_proxy = os.environ.get("JUJU_CHARM_HTTPS_PROXY")
    no_proxy = os.environ.get("JUJU_CHARM_NO_PROXY")
    java_tool_options = _get_java_tool_options(http_proxy, https_proxy, no_proxy)

    if http_proxy:
        env.update(
            {
                "HTTP_PROXY": http_proxy,
                "http_proxy": http_proxy,
                "JAVA_TOOL_OPTIONS": java_tool_options,
                "JOB_DEFAULT_ENV_http_proxy": http_proxy,
                "JOB_DEFAULT_ENV_HTTP_PROXY": http_proxy,
                "JOB_DEFAULT_ENV_JAVA_TOOL_OPTIONS": java_tool_options,
            }
        )

    if https_proxy:
        env.update(
            {
                "HTTPS_PROXY": https_proxy,
                "https_proxy": https_proxy,
                "JOB_DEFAULT_ENV_https_proxy": https_proxy,
                "JOB_DEFAULT_ENV_HTTPS_PROXY": https_proxy,
            }
        )

    if no_proxy:
        env.update(
            {
                "NO_PROXY": no_proxy,
                "no_proxy": no_proxy,
                "JOB_DEFAULT_ENV_no_proxy": no_proxy,
                "JOB_DEFAULT_ENV_NO_PROXY": no_proxy,
            }
        )

    return env


def _get_java_tool_options(http_proxy, https_proxy, no_proxy):
    options = ""
    if http_proxy:
        _, host, port = _split_url(http_proxy)
        options += f"-Dhttp.proxyHost={host} -Dhttp.proxyPort={port}"
    if https_proxy:
        _, host, port = _split_url(https_proxy)
        options += f" -Dhttps.proxyHost={host} -Dhttps.proxyPort={port}"
    if no_proxy:
        options += f" -Dhttp.nonProxyHosts={no_proxy.replace(',', '|')}"

    return options


def _split_url(url):
    parsed_url = urlparse(url)
    protocol = parsed_url.scheme
    host = parsed_url.hostname
    port = parsed_url.port
    return protocol, host, port


def construct_svc_endpoint(service_name, namespace, port, secure=False):
    """Construct the endpoint for a Kubernetes service.

    Args:
        service_name (str): The name of the Kubernetes service.
        namespace (str): The namespace of the Kubernetes service.
        port (int): The port number of the Kubernetes service.
        secure (bool): Whether to use HTTPS (true) or HTTP (false).

    Returns:
        str: The constructed S3 service endpoint.
    """
    protocol = "https" if secure else "http"
    return f"{protocol}://{service_name}.{namespace}.svc.cluster.local:{port}"
