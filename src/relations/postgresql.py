# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Airbyte server postgresql relation."""

import logging

from charms.data_platform_libs.v0.database_requires import DatabaseEvent
from literals import DB_NAME
from log import log_event_handler
from ops import framework
from ops.model import WaitingStatus

logger = logging.getLogger(__name__)


class PostgresqlRelation(framework.Object):
    """Client for airbyte:postgresql relations."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "db")
        self.charm = charm

        charm.framework.observe(charm.db.on.database_created, self._on_database_changed)
        charm.framework.observe(charm.db.on.endpoints_changed, self._on_database_changed)
        charm.framework.observe(charm.on.db_relation_broken, self._on_database_relation_broken)

    @log_event_handler(logger)
    def _on_database_changed(self, event: DatabaseEvent) -> None:
        """Handle database creation/change events.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm._state.is_ready():
            event.defer()
            return

        self.charm.unit.status = WaitingStatus(f"handling {event.relation.name} change")
        host, port = event.endpoints.split(",", 1)[0].split(":")

        self.charm._state.database_connection = {
            "dbname": DB_NAME,
            "host": host,
            "port": port,
            "password": event.password,
            "user": event.username,
        }

        self.charm._update(event)

    @log_event_handler(logger)
    def _on_database_relation_broken(self, event: DatabaseEvent) -> None:
        """Handle broken relations with the database.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm._state.is_ready():
            event.defer()
            return

        self.charm._state.database_connection = None
        self.charm._update(event)
