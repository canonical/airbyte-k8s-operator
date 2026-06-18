#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured config unit tests."""

import base64
import logging
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ops import testing

from charm import AirbyteK8SOperatorCharm
from src.literals import CONTAINER_HEALTH_CHECK_MAP

logger = logging.getLogger(__name__)


class TestCharmStructuredConfig(TestCase):
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

        self.ctx = testing.Context(AirbyteK8SOperatorCharm)
        self.containers = {
            testing.Container(container_name, can_connect=True) for container_name in CONTAINER_HEALTH_CHECK_MAP
        }

    def check_valid_values(self, field, accepted_values):
        """Check that the structured config parses each accepted value for a field.

        Args:
            field: The configuration field to test.
            accepted_values: List of accepted values for this field.
        """
        for value in accepted_values:
            state = testing.State(
                leader=True,
                config={field: value},
                model=testing.Model(name="airbyte-model"),
                containers=self.containers,
            )
            with self.ctx(self.ctx.on.config_changed(), state) as manager:
                self.assertEqual(manager.charm.config[field], value)

    def check_invalid_values(self, field, erroneus_values):
        """Check that the structured config rejects each invalid value for a field.

        Args:
            field: The configuration field to test.
            erroneus_values: List of invalid values for this field.
        """
        for value in erroneus_values:
            state = testing.State(
                leader=True,
                config={field: value},
                model=testing.Model(name="airbyte-model"),
                containers=self.containers,
            )
            with self.ctx(self.ctx.on.config_changed(), state) as manager:
                with self.assertRaises(ValueError):
                    _ = manager.charm.config[field]

    def test_config_parsing_parameters_integer_values(self) -> None:
        """Check that integer fields are parsed correctly."""
        integer_fields = [
            "logs-ttl",
            "pod-running-ttl-minutes",
            "pod-successful-ttl-minutes",
            "pod-unsuccessful-ttl-minutes",
        ]
        erroneus_values = [-5]
        valid_values = [42, 100, 1]
        for field in integer_fields:
            self.check_invalid_values(field, erroneus_values)
            self.check_valid_values(field, valid_values)

    def test_application_related_values(self) -> None:
        """Test specific parameters for application-related fields."""
        erroneus_values = ["test-value", "foo", "bar"]

        # storage-type
        self.check_invalid_values("storage-type", erroneus_values)
        accepted_values = ["MINIO", "S3"]
        self.check_valid_values("storage-type", accepted_values)

    def test_cpu_related_values(self) -> None:
        """Test specific parameters for cpu-related fields."""
        erroneus_values = ["-123", "0", "100f"]
        self.check_invalid_values("job-main-container-cpu-limit", erroneus_values)
        accepted_values = ["200m", "4"]
        self.check_valid_values("job-main-container-cpu-limit", accepted_values)

    def test_memory_related_values(self) -> None:
        """Test specific parameters for memory-related fields."""
        erroneus_values = ["-123", "0", "100f"]
        self.check_invalid_values("job-main-container-memory-limit", erroneus_values)
        accepted_values = ["4Gi", "256Mi"]
        self.check_valid_values("job-main-container-memory-limit", accepted_values)
