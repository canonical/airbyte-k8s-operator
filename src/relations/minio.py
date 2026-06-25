# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Airbyte server minio relation."""

import logging

from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from ops import framework
from ops.model import BlockedStatus, WaitingStatus
from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)

from charm_helpers import construct_svc_endpoint
from log import log_event_handler

logger = logging.getLogger(__name__)


class MinioRelation(framework.Object):
    """Client for airbyte:minio relation."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "object-storage")
        self.charm = charm

        # Handle minio relation.
        charm.framework.observe(charm.on.object_storage_relation_joined, self._on_object_storage_relation_changed)
        charm.framework.observe(charm.on.object_storage_relation_changed, self._on_object_storage_relation_changed)
        charm.framework.observe(charm.on.object_storage_relation_broken, self._on_object_storage_relation_broken)

    @log_event_handler(logger)
    def _on_object_storage_relation_changed(self, event):
        """Handle changing object-storage relation.

        Args:
            event: The event triggered when the relation changed.
        """
        self.charm.reconcile()

    @log_event_handler(logger)
    def _on_object_storage_relation_broken(self, event) -> None:
        """Handle broken relation with object-storage.

        Args:
            event: The event triggered when the relation changed.
        """
        self.charm.reconcile()

    def get_data(self):
        """Return live object-storage data from the relation, or None.

        Returns:
            object-storage connection data dict (with endpoint), or None if the
            relation is absent or its data is not yet available.
        """
        if not self.model.get_relation("object-storage"):
            return None
        try:
            interfaces = self._get_interfaces()
            storage_data = self._get_object_storage_data(interfaces)
        except ErrorWithStatus as err:
            logger.info("object-storage relation not ready: %s", str(err))
            return None

        endpoint = construct_svc_endpoint(
            storage_data["service"],
            storage_data["namespace"],
            storage_data["port"],
            storage_data["secure"],
        )
        return {**storage_data, "endpoint": endpoint}

    def _get_interfaces(self):
        """Retrieve interface object.

        Returns:
            list of charm interfaces.

        Raises:
            ErrorWithStatus: if an anticipated error occurs.
        """
        try:
            charm = self.charm
            # Hack: get_interfaces checks for peer relation which does not exist under
            # requires/provides list in charmcraft.yaml
            if "airbyte-peer" in charm.meta.relations:
                del charm.meta.relations["airbyte-peer"]
            interfaces = get_interfaces(charm)
        except NoVersionsListed as err:
            raise ErrorWithStatus(err, WaitingStatus) from err
        except NoCompatibleVersions as err:
            raise ErrorWithStatus(err, BlockedStatus) from err
        return interfaces

    def _get_object_storage_data(self, interfaces):
        """Unpacks and returns the object-storage relation data.

        Args:
            interfaces: list of charm interfaces.

        Returns:
            object storage connection data.

        Raises:
            ErrorWithStatus: if an anticipated error occurs.
        """
        if not ((obj_storage := interfaces["object-storage"]) and obj_storage.get_data()):
            raise ErrorWithStatus("Waiting for object-storage relation data", WaitingStatus)

        try:
            logger.info(f"obj_storage get_data: {obj_storage.get_data()}")
            obj_storage = list(obj_storage.get_data().values())[0]
        except Exception as e:
            raise ErrorWithStatus(
                f"Unexpected error unpacking object storage data - data format not "
                f"as expected. Caught exception: '{str(e)}'",
                BlockedStatus,
            ) from e

        return obj_storage
