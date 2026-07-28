#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# flake8: noqa

"""Structured configuration for the charm."""

import logging
import re
from enum import Enum

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from pydantic import field_validator

logger = logging.getLogger(__name__)


class LogLevelType(str, Enum):
    """Enum for the `log-level` field."""

    INFO = "INFO"
    DEBUG = "DEBUG"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class StorageType(str, Enum):
    """Enum for the `storage-type` field."""

    minio = "MINIO"
    s3 = "S3"


class SecretPersistenceType(str, Enum):
    """Enum for the `secret-persistence` field."""

    GOOGLE_SECRET_MANAGER = "GOOGLE_SECRET_MANAGER"  # nosec
    AWS_SECRET_MANAGER = "AWS_SECRET_MANAGER"  # nosec
    TESTING_CONFIG_DB_TABLE = "TESTING_CONFIG_DB_TABLE"
    VAULT = "VAULT"


class VaultAuthType(str, Enum):
    """Enum for the `vault-auth-method` field."""

    token = "token"  # nosec


class ImagePullPolicyType(str, Enum):
    """Enum for the `*-image-pull-policy` field."""

    Always = "Always"
    IfNotPresent = "IfNotPresent"
    Never = "Never"


class CharmConfig(BaseConfigModel):
    """Manager for the structured configuration."""

    log_level: LogLevelType
    temporal_host: str
    secret_persistence: SecretPersistenceType | None = None
    secret_store_gcp_project_id: str | None = None
    vault_address: str | None = None
    vault_prefix: str | None = None
    vault_auth_method: VaultAuthType
    aws_kms_key_arn: str | None = None
    aws_secret_manager_secret_tags: str | None = None
    aws_credentials_secret_id: str | None = None
    gcp_credentials_secret_id: str | None = None
    vault_token_secret_id: str | None = None
    sync_job_retries_complete_failures_max_successive: int | None = None
    sync_job_retries_complete_failures_max_total: int | None = None
    sync_job_retries_complete_failures_backoff_min_interval_s: int | None = None
    sync_job_retries_complete_failures_backoff_max_interval_s: int | None = None
    sync_job_retries_complete_failures_backoff_base: int | None = None
    sync_job_retries_partial_failures_max_successive: int | None = None
    sync_job_retries_partial_failures_max_total: int | None = None
    sync_job_max_timeout_days: int | None = None
    job_main_container_cpu_request: str | None = None
    job_main_container_cpu_limit: str | None = None
    job_main_container_memory_request: str | None = None
    job_main_container_memory_limit: str | None = None
    max_fields_per_connections: int | None = None
    max_days_of_only_failed_jobs_before_connection_disable: int | None = None
    max_failed_jobs_in_a_row_before_connection_disable: int | None = None
    max_spec_workers: int | None = None
    max_check_workers: int | None = None
    max_sync_workers: int | None = None
    max_discover_workers: int | None = None
    temporal_history_retention_in_days: int | None = None
    job_kube_tolerations: str | None = None
    job_kube_node_selectors: str | None = None
    job_kube_annotations: str | None = None
    job_kube_main_container_image_pull_policy: ImagePullPolicyType | None = None
    job_kube_main_container_image_pull_secret: str | None = None
    job_kube_sidecar_container_image_pull_policy: ImagePullPolicyType | None = None
    job_kube_socat_image: str | None = None
    job_kube_busybox_image: str | None = None
    job_kube_curl_image: str | None = None
    job_kube_namespace: str | None = None
    spec_job_kube_node_selectors: str | None = None
    check_job_kube_node_selectors: str | None = None
    discover_job_kube_node_selectors: str | None = None
    spec_job_kube_annotations: str | None = None
    check_job_kube_annotations: str | None = None
    discover_job_kube_annotations: str | None = None
    storage_type: StorageType
    storage_bucket_logs: str
    logs_ttl: int
    storage_bucket_state: str
    storage_bucket_activity_payload: str
    storage_bucket_workload_output: str
    storage_bucket_audit_logging: str
    pod_running_ttl_minutes: int
    pod_successful_ttl_minutes: int
    pod_unsuccessful_ttl_minutes: int

    @field_validator("*", mode="before")
    @classmethod
    def blank_string(cls, value):
        """Check for empty strings.

        Args:
            value: configuration value

        Returns:
            None in place of empty string or value
        """
        if value == "":
            return None
        return value

    @field_validator("pod_running_ttl_minutes", "pod_successful_ttl_minutes", "pod_unsuccessful_ttl_minutes")
    @classmethod
    def greater_than_zero(cls, value: str) -> int | None:
        """Check validity of `*-ttl-minutes` fields.

        Args:
            value: *-ttl-minutes value

        Returns:
            int_value: integer for *-ttl-minutes configuration

        Raises:
            ValueError: in the case when the value is out of range
        """
        int_value = int(value)
        if int_value > 0:
            return int_value
        raise ValueError("Value out of range.")

    @field_validator("logs_ttl")
    @classmethod
    def zero_or_greater(cls, value: str) -> int | None:
        """Check validity of `logs-ttl` fields.

        Args:
            value: logs-ttl value

        Returns:
            int_value: integer for logs-ttl configuration

        Raises:
            ValueError: in the case when the value is out of range
        """
        int_value = int(value)
        if int_value >= 0:
            return int_value
        raise ValueError("Value out of range.")

    @field_validator("job_main_container_cpu_request", "job_main_container_cpu_limit")
    @classmethod
    def cpu_validator(cls, value: str) -> str | None:
        """Check validity of `*-cpu-request/limit` fields.

        Args:
            value: CPU request/limit value

        Returns:
            value: CPU request/limit value

        Raises:
            ValueError: in the case when the value is invalid
        """
        millicores_pattern = re.compile(r"^\d+m$")

        if millicores_pattern.match(value):
            return value

        int_value = int(value)
        if int_value > 0:
            return value
        raise ValueError("Invalid CPU request/limit value.")

    @field_validator("job_main_container_memory_request", "job_main_container_memory_limit")
    @classmethod
    def memory_validator(cls, value: str) -> str | None:
        """Check validity of `*-memory-request/limit` fields.

        Args:
            value: Memory request/limit value

        Returns:
            value: Memory request/limit value

        Raises:
            ValueError: in the case when the value is invalid
        """
        memory_pattern = re.compile(r"^[1-9]\d*(Ei|Pi|Ti|Gi|Mi|Ki)?$")

        if memory_pattern.match(value):
            return value

        # Check if the input is a valid integer (bytes)
        int_value = int(value)
        if int_value > 0:
            return value
        raise ValueError("Invalid CPU request/limit value.")
