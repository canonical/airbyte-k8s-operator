# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""S3 relation implementation."""

import logging

import botocore
from charms.data_platform_libs.v0.s3 import (
    CredentialsChangedEvent,
    CredentialsGoneEvent,
)
from ops import framework

from log import log_event_handler

logger = logging.getLogger(__name__)


class S3Integrator(framework.Object):
    """Client for s3 relation."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "s3")
        self.charm = charm
        charm.framework.observe(charm.s3_client.on.credentials_changed, self._on_s3_credentials_changed)
        charm.framework.observe(charm.s3_client.on.credentials_gone, self._on_s3_credentials_gone)

    @log_event_handler(logger)
    def _on_s3_credentials_changed(self, event: CredentialsChangedEvent):
        """Handle new s3 relation.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        s3_parameters, missing_parameters = self._retrieve_s3_parameters()
        if missing_parameters:
            return

        endpoint = _construct_endpoint(s3_parameters)
        self.charm._state.s3 = {
            "bucket": s3_parameters.get("bucket"),
            "endpoint": endpoint,
            "region": s3_parameters.get("region"),
            "access-key": s3_parameters.get("access-key"),
            "secret-key": s3_parameters.get("secret-key"),
            "uri_style": s3_parameters.get("s3-uri-style"),
        }
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_s3_credentials_gone(self, event: CredentialsGoneEvent) -> None:
        """Handle s3 relation broken event.

        Args:
            event: The event triggered when the relation was broken.
        """
        if not self.charm.unit.is_leader():
            return

        self.charm._state.s3 = None
        self.charm._update(event)

    def _retrieve_s3_parameters(self):
        """Retrieve S3 parameters from the S3 integrator relation.

        Returns:
            s3 parameters (dict) and any missing parameters (list) from the relation.
        """
        s3_parameters = self.charm.s3_client.get_s3_connection_info()
        required_parameters = [
            "access-key",
            "secret-key",
        ]
        missing_required_parameters = [param for param in required_parameters if param not in s3_parameters]
        if missing_required_parameters:
            logger.warning(
                f"Missing required S3 parameters in relation with S3 integrator: {missing_required_parameters}"
            )
            return {}, missing_required_parameters

        # Add some sensible defaults (as expected by the code) for missing optional parameters
        s3_parameters.setdefault("endpoint", "https://s3.amazonaws.com")
        s3_parameters.setdefault("region", "")
        s3_parameters.setdefault("path", "")
        s3_parameters.setdefault("s3-uri-style", "host")

        # Strip whitespaces from all parameters.
        for key, value in s3_parameters.items():
            if isinstance(value, str):
                s3_parameters[key] = value.strip()

        # Clean up extra slash symbols to avoid issues on 3rd-party storages
        # like Ceph Object Gateway (radosgw).
        s3_parameters["endpoint"] = s3_parameters["endpoint"].rstrip("/")
        s3_parameters[
            "path"
        ] = f'/{s3_parameters["path"].strip("/")}'  # The slash in the beginning is required by pgBackRest.
        s3_parameters["bucket"] = s3_parameters["bucket"].strip("/")

        return s3_parameters, []


def _construct_endpoint(s3_parameters):
    """Construct the S3 service endpoint using the region.

    This is needed when the provided endpoint is from AWS, and it doesn't contain the region.

    Args:
        s3_parameters: s3 parameters fetched from the s3 integrator relation.

    Returns:
        S3 service endpoint.
    """
    # Use the provided endpoint if a region is not needed.
    endpoint = s3_parameters["endpoint"]

    # Load endpoints data.
    loader = botocore.loaders.create_loader()
    data = loader.load_data("endpoints")

    # Construct the endpoint using the region.
    resolver = botocore.regions.EndpointResolver(data)
    endpoint_data = resolver.construct_endpoint("s3", s3_parameters["region"])

    # Use the built endpoint if it is an AWS endpoint.
    if endpoint_data and endpoint.endswith(endpoint_data["dnsSuffix"]):
        endpoint = f'{endpoint.split("://")[0]}://{endpoint_data["hostname"]}'

    return endpoint
