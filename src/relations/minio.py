# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Airbyte server minio relation."""

import logging

from charm_helpers import construct_svc_endpoint
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from log import log_event_handler
from ops import framework
from ops.model import BlockedStatus, WaitingStatus
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces

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
        charm.framework.observe(
            charm.on.object_storage_relation_joined, self._on_object_storage_relation_changed
        )
        charm.framework.observe(
            charm.on.object_storage_relation_changed, self._on_object_storage_relation_changed
        )
        charm.framework.observe(
            charm.on.object_storage_relation_broken, self._on_object_storage_relation_broken
        )

    @log_event_handler(logger)
    def _on_object_storage_relation_changed(self, event):
        """Handle changing object-storage relation.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm._state.is_ready():
            event.defer()
            return

        try:
            interfaces = self._get_interfaces()
            storage_data = self._get_object_storage_data(interfaces)
            endpoint = construct_svc_endpoint(
                storage_data["service"],
                storage_data["namespace"],
                storage_data["port"],
                storage_data["secure"],
            )

            self.charm._state.minio = {
                **storage_data,
                "endpoint": endpoint,
            }
            self.charm._update(event)
        except ErrorWithStatus as err:
            self.charm.unit.status = err.status
            logger.error(f"Event {event} stopped early with message: {str(err)}")
            return

    @log_event_handler(logger)
    def _on_object_storage_relation_broken(self, event) -> None:
        """Handle broken relation with object-storage.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm._state.is_ready():
            event.defer()
            return

        self.charm._state.minio = None
        self.charm._update(event)

    def _get_interfaces(self):
        """Retrieve interface object."""
        try:
            charm = self.charm
            # Hack: get_interfaces checks for peer relation which does not exist under requires/provides list in charmcraft.yaml
            del charm.meta.relations["peer"]
            interfaces = get_interfaces(charm)
        except NoVersionsListed as err:
            raise ErrorWithStatus(err, WaitingStatus)
        except NoCompatibleVersions as err:
            raise ErrorWithStatus(err, BlockedStatus)
        return interfaces

    def _get_object_storage_data(self, interfaces):
        """Unpacks and returns the object-storage relation data.

        Raises CheckFailedError if an anticipated error occurs.
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
            )

        return obj_storage
