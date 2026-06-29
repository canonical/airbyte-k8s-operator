# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Airbyte server postgresql relation."""

import logging

from charms.data_platform_libs.v0.database_requires import DatabaseEvent
from ops import framework

from connections import DatabaseConnection
from literals import DB_NAME
from log import log_event_handler

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
        self.charm.reconcile()

    @log_event_handler(logger)
    def _on_database_relation_broken(self, event: DatabaseEvent) -> None:
        """Handle broken relations with the database.

        Args:
            event: The event triggered when the relation changed.
        """
        self.charm.reconcile()

    def get_data(self) -> DatabaseConnection | None:
        """Return the live database connection details, or None.

        Returns:
            A DatabaseConnection derived from the db relation, or None if the
            relation is absent or not yet ready.
        """
        relation = self.model.get_relation("db")
        if relation is None:
            return None
        data = self.charm.db.fetch_relation_data().get(relation.id, {})
        endpoints = data.get("endpoints")
        if not endpoints:
            return None
        host, port = endpoints.split(",", 1)[0].split(":")
        return DatabaseConnection(
            dbname=DB_NAME,
            host=host,
            port=port,
            user=data.get("username"),
            password=data.get("password"),
        )
