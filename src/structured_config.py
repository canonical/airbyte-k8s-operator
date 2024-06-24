#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# flake8: noqa

"""Structured configuration for the charm."""

import logging
import re
from enum import Enum
from typing import Optional

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from pydantic import validator

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

    secret_persistence: Optional["SecretPersistenceType"] = None  # Optional field


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
    webapp_url: Optional[str]
    secret_persistence: Optional[SecretPersistenceType]
    secret_store_gcp_project_id: Optional[str]
    secret_store_gcp_credentials: Optional[str]
    vault_address: Optional[str]
    vault_prefix: Optional[str]
    vault_auth_token: Optional[str]
    vault_auth_method: VaultAuthType
    aws_access_key: Optional[str]
    aws_secret_access_key: Optional[str]
    aws_kms_key_arn: Optional[str]
    aws_secret_manager_secret_tags: Optional[str]
    sync_job_retries_complete_failures_max_successive: Optional[int]
    sync_job_retries_complete_failures_max_total: Optional[int]
    sync_job_retries_complete_failures_backoff_min_interval_s: Optional[int]
    sync_job_retries_complete_failures_backoff_max_interval_s: Optional[int]
    sync_job_retries_complete_failures_backoff_base: Optional[int]
    sync_job_retries_partial_failures_max_successive: Optional[int]
    sync_job_retries_partial_failures_max_total: Optional[int]
    sync_job_max_timeout_days: Optional[int]
    job_main_container_cpu_request: Optional[str]
    job_main_container_cpu_limit: Optional[str]
    job_main_container_memory_request: Optional[str]
    job_main_container_memory_limit: Optional[str]
    max_fields_per_connections: Optional[int]
    max_days_of_only_failed_jobs_before_connection_disable: Optional[int]
    max_failed_jobs_in_a_row_before_connection_disable: Optional[int]
    max_spec_workers: Optional[int]
    max_check_workers: Optional[int]
    max_sync_workers: Optional[int]
    max_discover_workers: Optional[int]
    temporal_history_retention_in_days: Optional[int]
    job_kube_tolerations: Optional[str]
    job_kube_node_selectors: Optional[str]
    job_kube_annotations: Optional[str]
    job_kube_main_container_image_pull_policy: Optional[ImagePullPolicyType]
    job_kube_main_container_image_pull_secret: Optional[str]
    job_kube_sidecar_container_image_pull_policy: Optional[ImagePullPolicyType]
    job_kube_socat_image: Optional[str]
    job_kube_busybox_image: Optional[str]
    job_kube_curl_image: Optional[str]
    job_kube_namespace: Optional[str]
    spec_job_kube_node_selectors: Optional[str]
    check_job_kube_node_selectors: Optional[str]
    discover_job_kube_node_selectors: Optional[str]
    spec_job_kube_annotations: Optional[str]
    check_job_kube_annotations: Optional[str]
    discover_job_kube_annotations: Optional[str]
    storage_type: StorageType
    storage_bucket_logs: str
    logs_ttl: int
    storage_bucket_state: str
    storage_bucket_activity_payload: str
    storage_bucket_workload_output: str
    pod_running_ttl_minutes: int
    pod_successful_ttl_minutes: int
    pod_unsuccessful_ttl_minutes: int

    @validator("*", pre=True)
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

    @validator("pod_running_ttl_minutes", "pod_successful_ttl_minutes", "pod_unsuccessful_ttl_minutes")
    @classmethod
    def greater_than_zero(cls, value: str) -> Optional[int]:
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

    @validator("logs_ttl")
    @classmethod
    def zero_or_greater(cls, value: str) -> Optional[int]:
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

    @validator("job_main_container_cpu_request", "job_main_container_cpu_limit")
    @classmethod
    def cpu_validator(cls, value: str) -> Optional[str]:
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

    @validator("job_main_container_memory_request", "job_main_container_memory_limit")
    @classmethod
    def memory_validator(cls, value: str) -> Optional[str]:
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
