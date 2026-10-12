# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Airbyte API client."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from airbyte_client import AirbyteClient


def response(status_code: int, body: dict | None = None) -> MagicMock:
    """Build a fake HTTP response.

    Args:
        status_code: the HTTP status code.
        body: the JSON body.

    Returns:
        The fake response.
    """
    fake = MagicMock()
    fake.status_code = status_code
    fake.ok = 200 <= status_code < 300
    fake.json.return_value = body or {}
    return fake


@patch("airbyte_client.requests.request")
class TestGetConnector(TestCase):
    """Unit tests for AirbyteClient.get_connector."""

    def test_returns_connector(self, request):
        """An existing connector is returned."""
        body = {"sourceId": "s-1", "configuration": {"database": "db1"}}
        request.return_value = response(200, body)
        self.assertEqual(AirbyteClient().get_connector("source", "s-1"), body)

    def test_not_found(self, request):
        """A 404 means the connector does not exist."""
        request.return_value = response(404)
        self.assertIsNone(AirbyteClient().get_connector("source", "s-1"))

    def test_deleted_connector(self, request):
        """A deleted connector is still returned by Airbyte, with a null configuration."""
        request.return_value = response(200, {"sourceId": "s-1", "configuration": None})
        self.assertIsNone(AirbyteClient().get_connector("source", "s-1"))
