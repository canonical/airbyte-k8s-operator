# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for building Airbyte Postgres connector configurations."""

from unittest import TestCase

from connector_configuration import (
    ProviderData,
    build_configuration,
    build_host,
    merge_jdbc_params,
)
from structured_config import SourceConfig


class TestConnectorConfiguration(TestCase):
    """Tests for building connector configurations."""

    def test_build_host_multi_host(self):
        """Every host but the last carries its port; the last uses the port field."""
        host, port = build_host(["b:5432", "a:6432", "b:5432"])
        self.assertEqual((host, port), ("a:6432,b", 5432))

    def test_build_host_single(self):
        """A single endpoint maps directly to host and port."""
        self.assertEqual(build_host(["a:5432"]), ("a", 5432))

    def test_build_host_invalid(self):
        """No endpoints or an endpoint without a port raise ValueError."""
        for endpoints in ([], ["a"], ["a:port"]):
            with self.subTest(endpoints=endpoints), self.assertRaises(ValueError):
                build_host(endpoints)

    def test_merge_jdbc_params_keeps_user_params(self):
        """User params are appended to the charm-managed targetServerType."""
        self.assertEqual(
            merge_jdbc_params("primary", "connectTimeout=10&socketTimeout=5"),
            "targetServerType=primary&connectTimeout=10&socketTimeout=5",
        )

    def test_merge_jdbc_params_drops_override(self):
        """A user-supplied targetServerType is dropped."""
        self.assertEqual(
            merge_jdbc_params("preferSecondary", "TargetServerType=any&connectTimeout=10"),
            "targetServerType=preferSecondary&connectTimeout=10",
        )

    def test_build_configuration_tls_modes(self):
        """ssl_mode follows the provider's TLS settings."""
        entry = SourceConfig(database_prefix="db*", schemas=["public"])
        base = {
            "endpoints": "pg-primary:5432",
            "read_only_endpoints": "",
            "databases": ["db"],
            "username": "u",
            "password": "p",  # nosec B105
        }
        cases = [
            ((False, None), {"mode": "disable"}),
            ((True, None), {"mode": "require"}),
            ((True, "CA"), {"mode": "verify-ca", "ca_certificate": "CA"}),
        ]
        for (tls, ca), expected in cases:
            provider = ProviderData(**base, tls=tls, tls_ca=ca)
            self.assertEqual(build_configuration("source", entry, provider, "db")["ssl_mode"], expected)
