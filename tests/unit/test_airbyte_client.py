# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Airbyte API client."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests

from airbyte_client import AirbyteAPIError, AirbyteClient


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


@patch("airbyte_client.requests.request")
class TestResponseHandling(TestCase):
    """Unit tests for health checks and invalid JSON responses."""

    def test_healthy(self, request):
        """The server is healthy when the health endpoint reports available."""
        request.return_value = response(200, {"available": True})
        self.assertTrue(AirbyteClient().is_healthy())

    def test_unhealthy_on_error_status(self, request):
        """An error status means the server is not healthy."""
        request.return_value = response(502)
        self.assertFalse(AirbyteClient().is_healthy())

    def test_unhealthy_on_invalid_json(self, request):
        """A non-JSON health response means the server is not healthy."""
        fake = response(200)
        fake.json.side_effect = requests.JSONDecodeError("Expecting value", "<html>", 0)
        request.return_value = fake
        self.assertFalse(AirbyteClient().is_healthy())

    def test_invalid_json_raises_api_error(self, request):
        """A non-JSON API response raises AirbyteAPIError."""
        fake = response(200)
        fake.json.side_effect = requests.JSONDecodeError("Expecting value", "<html>", 0)
        request.return_value = fake
        with self.assertRaises(AirbyteAPIError):
            AirbyteClient().get_connector("source", "s-1")


@patch("airbyte_client.requests.request")
class TestErrorMessages(TestCase):
    """Unit tests for the messages of API errors."""

    def test_error_body_not_included(self, request):
        """Error messages keep the status and title but not the body."""
        fake = response(422, {"title": "unprocessable-entity", "detail": "invalid password 'hunter2'"})
        fake.text = '{"title": "unprocessable-entity", "detail": "invalid password \'hunter2\'"}'
        request.return_value = fake
        with self.assertRaises(AirbyteAPIError) as err:
            AirbyteClient().get_connector("source", "s-1")
        self.assertIn("422 unprocessable-entity", str(err.exception))
        self.assertNotIn("hunter2", str(err.exception))

    def test_error_without_json_body(self, request):
        """Error responses without a JSON body report the status only."""
        fake = response(500)
        fake.json.side_effect = requests.JSONDecodeError("Expecting value", "<html>", 0)
        request.return_value = fake
        with self.assertRaises(AirbyteAPIError) as err:
            AirbyteClient().get_connector("source", "s-1")
        self.assertTrue(str(err.exception).endswith("500"))
