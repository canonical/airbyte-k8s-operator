# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Airbyte server:ui relation."""

import logging

from ops import framework
from ops.model import ActiveStatus

from log import log_event_handler

logger = logging.getLogger(__name__)


class AirbyteServerProvider(framework.Object):
    """Client for server:ui relation."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "airbyte-server")
        self.charm = charm
        charm.framework.observe(charm.on.airbyte_server_relation_joined, self._on_airbyte_server_relation_joined)
        charm.framework.observe(charm.on.airbyte_server_relation_changed, self._on_airbyte_server_relation_joined)

    @log_event_handler(logger)
    def _on_airbyte_server_relation_joined(self, event):
        """Handle new server:ui relation.

        Attempt to provide server status to the ui application.

        Args:
            event: The event triggered when the relation changed.
        """
        if self.charm.unit.is_leader():
            self._provide_server_status()

    def _provide_server_status(self):
        """Provide server status to the UI charm."""
        is_active = self.charm.model.unit.status == ActiveStatus()

        ui_relations = self.charm.model.relations["airbyte-server"]
        if not ui_relations:
            logger.debug("server:ui: not providing server status: ui not ready")
            return
        for relation in ui_relations:
            logger.debug(f"server:ui: providing server status on relation {relation.id}")
            relation.data[self.charm.app].update(
                {
                    "server_name": self.charm.app.name,
                    "server_status": "ready" if is_active else "blocked",
                }
            )
