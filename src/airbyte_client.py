# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Minimal client for the Airbyte public API served by the local airbyte-server."""

import logging

import requests

from literals import INTERNAL_API_PORT

logger = logging.getLogger(__name__)

API_URL = f"http://localhost:{INTERNAL_API_PORT}"
REQUEST_TIMEOUT = 30
# Creating or updating a connector may run a spec job for its image on first use.
WRITE_TIMEOUT = 300

CONNECTOR_PATHS = {"source": "sources", "destination": "destinations"}


class AirbyteAPIError(Exception):
    """Raised when the Airbyte API is unreachable or returns an error."""


class AirbyteClient:
    """Client for the Airbyte public API (`/api/public/v1`)."""

    def __init__(self, base_url: str = API_URL):
        """Construct.

        Args:
            base_url: Base URL of the Airbyte server.
        """
        self.base_url = base_url

    def _request(self, method: str, path: str, *, timeout: int = REQUEST_TIMEOUT, **kwargs) -> requests.Response:
        """Send a request to the Airbyte API.

        Args:
            method: HTTP method.
            path: Path relative to the base URL.
            timeout: Request timeout in seconds.
            kwargs: Extra arguments passed to `requests.request`.

        Returns:
            The HTTP response.

        Raises:
            AirbyteAPIError: If the server cannot be reached.
        """
        try:
            return requests.request(
                method,
                f"{self.base_url}{path}",
                headers={"accept": "application/json"},
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as err:
            raise AirbyteAPIError(f"{method} {path} failed: {err}") from err

    @staticmethod
    def _json(response: requests.Response) -> dict:
        """Return the JSON body of a successful response.

        Args:
            response: The HTTP response.

        Returns:
            The decoded JSON body.

        Raises:
            AirbyteAPIError: If the response is not successful.
        """
        if not response.ok:
            raise AirbyteAPIError(
                f"{response.request.method} {response.url} returned {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    def is_healthy(self) -> bool:
        """Return whether the Airbyte server reports itself available.

        Returns:
            True if the health endpoint reports available.
        """
        try:
            response = self._request("GET", "/api/v1/health", timeout=10)
        except AirbyteAPIError:
            return False
        return response.ok and bool(response.json().get("available"))

    def get_workspace_id(self, name: str | None = None) -> str:
        """Return the ID of a workspace by name, or of the first workspace.

        Args:
            name: Workspace name; the first workspace is used when not set.

        Returns:
            The workspace ID.

        Raises:
            AirbyteAPIError: If no matching workspace exists.
        """
        response = self._request("GET", "/api/public/v1/workspaces", params={"limit": 100})
        workspaces = self._json(response).get("data", [])
        for workspace in workspaces:
            if name is None or workspace.get("name") == name:
                return workspace["workspaceId"]
        raise AirbyteAPIError(f"workspace {name!r} not found" if name else "no workspace found")

    def get_connector(self, connector_type: str, connector_id: str) -> dict | None:
        """Return a source or destination, or None if it does not exist.

        Args:
            connector_type: "source" or "destination".
            connector_id: The connector ID.

        Returns:
            The connector, or None if Airbyte returns 404.
        """
        response = self._request("GET", f"/api/public/v1/{CONNECTOR_PATHS[connector_type]}/{connector_id}")
        if response.status_code == 404:
            return None
        return self._json(response)

    def create_connector(self, connector_type: str, workspace_id: str, name: str, configuration: dict) -> str:
        """Create a source or destination.

        Args:
            connector_type: "source" or "destination".
            workspace_id: The workspace to create the connector in.
            name: The connector name.
            configuration: The connector configuration.

        Returns:
            The ID of the created connector.
        """
        response = self._request(
            "POST",
            f"/api/public/v1/{CONNECTOR_PATHS[connector_type]}",
            json={"name": name, "workspaceId": workspace_id, "configuration": configuration},
            timeout=WRITE_TIMEOUT,
        )
        return self._json(response)[f"{connector_type}Id"]

    def update_connector(self, connector_type: str, connector_id: str, name: str, configuration: dict) -> None:
        """Update the name and configuration of a source or destination.

        Args:
            connector_type: "source" or "destination".
            connector_id: The connector ID.
            name: The connector name.
            configuration: The connector configuration.
        """
        response = self._request(
            "PATCH",
            f"/api/public/v1/{CONNECTOR_PATHS[connector_type]}/{connector_id}",
            json={"name": name, "configuration": configuration},
            timeout=WRITE_TIMEOUT,
        )
        self._json(response)
