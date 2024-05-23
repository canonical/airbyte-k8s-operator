#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the Superset charm."""
import logging
from enum import Enum
from typing import Optional

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from pydantic import validator

logger = logging.getLogger(__name__)


class BaseEnumStr(str, Enum):
    """Base class for string enum."""

    def __str__(self) -> str:
        """Return the value as a string.

        Returns:
            string of config value
        """
        return str(self.value)


class LogLevelType(str, Enum):
    """Enum for the `log-level` field."""

    INFO = "INFO"
    DEBUG = "DEBUG"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class StorageType(str, Enum):
    """Enum for the `storage-type` field."""

    minio = "minio"


class CharmConfig(BaseConfigModel):
    """Manager for the structured configuration."""

    log_level: LogLevelType
    temporal_host: str
    storage_type: StorageType
    storage_bucket_log: str
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
    def ttl_minutes_validator(cls, value: str) -> Optional[int]:
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
