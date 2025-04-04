# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm helpers."""

import os
from urllib.parse import urlparse

from literals import (
    AIRBYTE_API_PORT,
    BASE_ENV,
    CONNECTOR_BUILDER_SERVER_API_PORT,
    INTERNAL_API_PORT,
    WORKLOAD_API_PORT,
)
from structured_config import StorageType


def create_env(model_name, app_name, container_name, config, state):
    """Create set of environment variables for application.

    Args:
        model_name: Name of the juju model.
        app_name: Name of the application.
        container_name: Name of Airbyte container.
        config: Charm config.
        state: Charm state.

    Returns:
        environment variables dict.
    """
    db_conn = state.database_connection

    host = db_conn["host"]
    port = db_conn["port"]
    db_name = db_conn["dbname"]
    db_url = f"jdbc:postgresql://{host}:{port}/{db_name}"
    secret_persistence = config["secret-persistence"]
    if secret_persistence:
        secret_persistence = config["secret-persistence"].value

    # Some defaults are extracted from Helm chart:
    # https://github.com/airbytehq/airbyte-platform/tree/v1.5.0/charts/airbyte
    env = {
        **BASE_ENV,
        # Airbye services config
        "LOG_LEVEL": config["log-level"].value,
        "TEMPORAL_HOST": config["temporal-host"],
        "WEBAPP_URL": config["webapp-url"],
        # Secrets config
        "SECRET_PERSISTENCE": secret_persistence,
        "SECRET_STORE_GCP_PROJECT_ID": config["secret-store-gcp-project-id"],
        "SECRET_STORE_GCP_CREDENTIALS": config["secret-store-gcp-credentials"],
        "VAULT_ADDRESS": config["vault-address"],
        "VAULT_PREFIX": config["vault-prefix"],
        "VAULT_AUTH_TOKEN": config["vault-auth-token"],
        "VAULT_AUTH_METHOD": config["vault-auth-method"].value,
        "AWS_ACCESS_KEY": config["aws-access-key"],
        "AWS_SECRET_ACCESS_KEY": config["aws-secret-access-key"],
        "AWS_KMS_KEY_ARN": config["aws-kms-key-arn"],
        "AWS_SECRET_MANAGER_SECRET_TAGS": config["aws-secret-manager-secret-tags"],
        # Jobs config
        "SYNC_JOB_RETRIES_COMPLETE_FAILURES_MAX_SUCCESSIVE": config[
            "sync-job-retries-complete-failures-max-successive"
        ],
        "SYNC_JOB_RETRIES_COMPLETE_FAILURES_MAX_TOTAL": config["sync-job-retries-complete-failures-max-total"],
        "SYNC_JOB_RETRIES_COMPLETE_FAILURES_BACKOFF_MIN_INTERVAL_S": config[
            "sync-job-retries-complete-failures-backoff-min-interval-s"
        ],
        "SYNC_JOB_RETRIES_COMPLETE_FAILURES_BACKOFF_MAX_INTERVAL_S": config[
            "sync-job-retries-complete-failures-backoff-max-interval-s"
        ],
        "SYNC_JOB_RETRIES_COMPLETE_FAILURES_BACKOFF_BASE": config["sync-job-retries-complete-failures-backoff-base"],
        "SYNC_JOB_RETRIES_PARTIAL_FAILURES_MAX_SUCCESSIVE": config["sync-job-retries-partial-failures-max-successive"],
        "SYNC_JOB_RETRIES_PARTIAL_FAILURES_MAX_TOTAL": config["sync-job-retries-partial-failures-max-total"],
        "SYNC_JOB_MAX_TIMEOUT_DAYS": config["sync-job-max-timeout-days"],
        "JOB_MAIN_CONTAINER_CPU_REQUEST": config["job-main-container-cpu-request"],
        "JOB_MAIN_CONTAINER_CPU_LIMIT": config["job-main-container-cpu-limit"],
        "JOB_MAIN_CONTAINER_MEMORY_REQUEST": config["job-main-container-memory-request"],
        "JOB_MAIN_CONTAINER_MEMORY_LIMIT": config["job-main-container-memory-limit"],
        # Connections config
        "MAX_FIELDS_PER_CONNECTION": config["max-fields-per-connections"],
        "MAX_DAYS_OF_ONLY_FAILED_JOBS_BEFORE_CONNECTION_DISABLE": config[
            "max-days-of-only-failed-jobs-before-connection-disable"
        ],
        "MAX_FAILED_JOBS_IN_A_ROW_BEFORE_CONNECTION_DISABLE": config[
            "max-failed-jobs-in-a-row-before-connection-disable"
        ],
        # Worker config
        "MAX_SPEC_WORKERS": config["max-spec-workers"],
        "MAX_CHECK_WORKERS": config["max-check-workers"],
        "MAX_SYNC_WORKERS": config["max-sync-workers"],
        "MAX_DISCOVER_WORKERS": config["max-discover-workers"],
        # Data retention config
        "TEMPORAL_HISTORY_RETENTION_IN_DAYS": config["temporal-history-retention-in-days"],
        # Kubernetes config
        "JOB_KUBE_TOLERATIONS": config["job-kube-tolerations"],
        "JOB_KUBE_NODE_SELECTORS": config["job-kube-node-selectors"],
        "JOB_KUBE_ANNOTATIONS": config["job-kube-annotations"],
        "JOB_KUBE_MAIN_CONTAINER_IMAGE_PULL_POLICY": config["job-kube-main-container-image-pull-policy"].value,
        "JOB_KUBE_MAIN_CONTAINER_IMAGE_PULL_SECRET": config["job-kube-main-container-image-pull-secret"],
        "JOB_KUBE_SIDECAR_CONTAINER_IMAGE_PULL_POLICY": config["job-kube-sidecar-container-image-pull-policy"].value,
        "JOB_KUBE_SOCAT_IMAGE": config["job-kube-socat-image"],
        "JOB_KUBE_BUSYBOX_IMAGE": config["job-kube-busybox-image"],
        "JOB_KUBE_CURL_IMAGE": config["job-kube-curl-image"],
        "JOB_KUBE_NAMESPACE": config["job-kube-namespace"] or model_name,
        # Jobs config
        "SPEC_JOB_KUBE_NODE_SELECTORS": config["spec-job-kube-node-selectors"],
        "CHECK_JOB_KUBE_NODE_SELECTORS": config["check-job-kube-node-selectors"],
        "DISCOVER_JOB_KUBE_NODE_SELECTORS": config["discover-job-kube-node-selectors"],
        "SPEC_JOB_KUBE_ANNOTATIONS": config["spec-job-kube-annotations"],
        "CHECK_JOB_KUBE_ANNOTATIONS": config["check-job-kube-annotations"],
        "DISCOVER_JOB_KUBE_ANNOTATIONS": config["discover-job-kube-annotations"],
        # Logging config
        "WORKER_LOGS_STORAGE_TYPE": config["storage-type"].value,
        "WORKER_STATE_STORAGE_TYPE": config["storage-type"].value,
        "STORAGE_TYPE": config["storage-type"].value,
        "STORAGE_BUCKET_LOG": config["storage-bucket-logs"],
        "S3_LOG_BUCKET": config["storage-bucket-logs"],
        "STORAGE_BUCKET_STATE": config["storage-bucket-state"],
        "STORAGE_BUCKET_WORKLOAD_OUTPUT": config["storage-bucket-workload-output"],
        "STORAGE_BUCKET_ACTIVITY_PAYLOAD": config["storage-bucket-activity-payload"],
        # Database config
        "DATABASE_URL": db_url,
        "DATABASE_USER": db_conn["user"],
        "DATABASE_PASSWORD": db_conn["password"],
        "DATABASE_DB": db_name,
        "DATABASE_HOST": host,
        "DATABASE_PORT": port,
        "KEYCLOAK_DATABASE_URL": db_url + "?currentSchema=keycloak",
        "JOB_KUBE_SERVICEACCOUNT": app_name,
        "RUNNING_TTL_MINUTES": config["pod-running-ttl-minutes"],
        "SUCCEEDED_TTL_MINUTES": config["pod-successful-ttl-minutes"],
        "UNSUCCESSFUL_TTL_MINUTES": config["pod-unsuccessful-ttl-minutes"],
        "INTERNAL_API_HOST": f"http://{app_name}:{INTERNAL_API_PORT}",
        "AIRBYTE_SERVER_HOST": f"{app_name}:{INTERNAL_API_PORT}",
        "CONFIG_API_HOST": f"{app_name}:{INTERNAL_API_PORT}",
        "CONNECTOR_BUILDER_SERVER_API_HOST": f"{app_name}:{CONNECTOR_BUILDER_SERVER_API_PORT}",
        "CONNECTOR_BUILDER_API_HOST": f"{app_name}:{CONNECTOR_BUILDER_SERVER_API_PORT}",
        "AIRBYTE_API_HOST": f"{app_name}:{AIRBYTE_API_PORT}/api/public",
        "WORKLOAD_API_HOST": f"{app_name}:{WORKLOAD_API_PORT}",
        "WORKLOAD_API_BEARER_TOKEN": ".Values.workload-api.bearerToken",
    }

    # https://github.com/airbytehq/airbyte/issues/29506#issuecomment-1775148609
    if container_name in ["airbyte-workload-launcher", "airbyte-workers"]:
        env.update(
            {
                "INTERNAL_API_HOST": f"http://{app_name}:{INTERNAL_API_PORT}",
                "WORKLOAD_API_HOST": f"http://{app_name}:{WORKLOAD_API_PORT}",
            }
        )

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
    """Generate Java tool options for configuring HTTP and HTTPS proxies.

    Args:
        http_proxy: The HTTP proxy URL.
        https_proxy: The HTTPS proxy URL.
        no_proxy: A comma-separated string of hosts that should bypass the proxy.

    Returns:
        A string of Java tool options for the provided proxy settings.

    Raises:
        ValueError: If any provided proxy URL is invalid or cannot be parsed.
    """
    options = ""
    try:
        if http_proxy:
            _, host, port = _split_url(http_proxy)
            options += f"-Dhttp.proxyHost={host} -Dhttp.proxyPort={port}"
        if https_proxy:
            _, host, port = _split_url(https_proxy)
            options += f" -Dhttps.proxyHost={host} -Dhttps.proxyPort={port}"
        if no_proxy:
            options += f" -Dhttp.nonProxyHosts={no_proxy.replace(',', '|')}"
    except Exception as e:
        raise ValueError(f"Invalid proxy URL: {e}") from e

    return options


def _split_url(url):
    """Split the given URL into its components: protocol, host, and port.

    Args:
        url: The URL to be split.

    Returns:
        tuple: A tuple containing the protocol, host, and port.

    Raises:
        ValueError: If the URL is invalid or cannot be parsed.
    """
    try:
        parsed_url = urlparse(url)
        protocol = parsed_url.scheme
        host = parsed_url.hostname
        port = parsed_url.port

        if not protocol or not host:
            raise ValueError("Invalid URL: Protocol or host is missing")

        return protocol, host, port
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}") from e


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
