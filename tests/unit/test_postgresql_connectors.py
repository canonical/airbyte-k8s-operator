# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the postgresql-source/destination connector relations."""

# pylint:disable=protected-access,too-many-public-methods

import dataclasses
import json
from unittest import TestCase
from unittest.mock import patch

import yaml
from ops import testing

from airbyte_client import AirbyteAPIError
from charm import AirbyteK8SOperatorCharm
from literals import MANAGED_CONNECTORS_KEY

PG_APP = "sales-db"
PRIMARY = "pg-primary.model.svc.cluster.local:5432"
REPLICAS = "pg-replicas.model.svc.cluster.local:5432"


class FakeAirbyte:
    """In-memory stand-in for the Airbyte public API client.

    Attrs:
        connectors: connectors keyed by ID.
        healthy: whether the server reports itself available.
        unreachable: whether every call raises AirbyteAPIError.
        calls: the write calls made, as (method, type, id) tuples.
        next_id: counter used to generate connector IDs.
    """

    def __init__(self):
        """Construct."""
        self.connectors: dict[str, dict] = {}
        self.healthy = True
        self.unreachable = False
        self.calls: list[tuple] = []
        self.next_id = 0

    def is_healthy(self):
        """Return whether the server is healthy.

        Returns:
            The configured health.
        """
        return self.healthy

    def get_workspace_id(self, name=None):
        """Return a fixed workspace ID.

        Args:
            name: the workspace name.

        Returns:
            The workspace ID.
        """
        return f"ws-{name}" if name else "ws-1"

    def get_connector(self, connector_type, connector_id):
        """Return a connector or None.

        Args:
            connector_type: "source" or "destination".
            connector_id: the connector ID.

        Returns:
            The connector or None.

        Raises:
            AirbyteAPIError: if the server is unreachable.
        """
        if self.unreachable:
            raise AirbyteAPIError("unreachable")
        return self.connectors.get(connector_id)

    def create_connector(self, connector_type, workspace_id, name, configuration):
        """Create a connector.

        Args:
            connector_type: "source" or "destination".
            workspace_id: the workspace ID.
            name: the connector name.
            configuration: the connector configuration.

        Returns:
            The new connector ID.
        """
        self.next_id += 1
        connector_id = f"{connector_type}-{self.next_id}"
        self.connectors[connector_id] = {"name": name, "workspaceId": workspace_id, "configuration": configuration}
        self.calls.append(("create", connector_type, connector_id))
        return connector_id

    def update_connector(self, connector_type, connector_id, name, configuration):
        """Update a connector.

        Args:
            connector_type: "source" or "destination".
            connector_id: the connector ID.
            name: the connector name.
            configuration: the connector configuration.
        """
        self.connectors[connector_id].update(name=name, configuration=configuration)
        self.calls.append(("update", connector_type, connector_id))


def user_secret(password="pw"):  # nosec B107
    """Return a remote-owned secret holding relation user credentials.

    Args:
        password: the password in the secret's latest revision.

    Returns:
        A testing.Secret.
    """
    return testing.Secret(
        tracked_content={"username": "relation-5", "password": "pw"},  # nosec B105
        latest_content={"username": "relation-5", "password": password},
    )


def pg_relation(secret, endpoint="postgresql-source", databases="dbaas_a,dbaas_b", tls=None, app=PG_APP):
    """Return a PostgreSQL relation with provider data.

    Args:
        secret: the user secret referenced by the relation.
        endpoint: the Airbyte endpoint.
        databases: the matched databases.
        tls: optional TLS secret.
        app: the remote application name.

    Returns:
        A testing.Relation.
    """
    data = {
        "endpoints": PRIMARY,
        "read-only-endpoints": REPLICAS,
        "prefix-databases": databases,
        "secret-user": secret.id,
    }
    if tls is not None:
        data["secret-tls"] = tls.id
    return testing.Relation(endpoint, remote_app_name=app, remote_app_data=data)


def make_state(*relations, secrets=(), config=None, tracked=None, leader=True):
    """Build a state with the peer relation and the given relations.

    Args:
        relations: relations to add.
        secrets: secrets to add.
        config: charm config.
        tracked: managed-connectors to pre-populate.
        leader: whether the unit is the leader.

    Returns:
        A testing.State.
    """
    peer_data = {MANAGED_CONNECTORS_KEY: json.dumps(tracked)} if tracked is not None else {}
    peer = testing.PeerRelation("airbyte-peer", local_app_data=peer_data)
    return testing.State(
        leader=leader,
        config=config if config is not None else source_config(),
        relations=[peer, *relations],
        secrets=list(secrets),
    )


def source_config(**settings):
    """Return charm config with a postgresql-source-config entry for PG_APP.

    Args:
        settings: entry settings, defaulting to a valid prefix.

    Returns:
        Charm config.
    """
    entry = {"database_prefix": "dbaas*", "schemas": ["public"], **settings}
    return {"postgresql-source-config": yaml.safe_dump({PG_APP: entry})}


def tracked_state(state):
    """Return the managed-connectors stored in the peer relation.

    Args:
        state: the output state.

    Returns:
        Tracked connectors.
    """
    peer = state.get_relations("airbyte-peer")[0]
    return json.loads(peer.local_app_data.get(MANAGED_CONNECTORS_KEY, "{}"))


class TestPostgresqlConnectors(TestCase):
    """Tests for the connector reconciliation and action."""

    def setUp(self):
        """Patch Kubernetes, the Airbyte client and the main reconcile."""
        for target in ("kubernetes.config.load_incluster_config", "kubernetes.client.CoreV1Api"):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.airbyte = FakeAirbyte()
        patcher = patch("relations.postgresql_connectors.AirbyteClient", return_value=self.airbyte)
        patcher.start()
        self.addCleanup(patcher.stop)

        # Only exercise connector reconciliation, not the workload.
        patcher = patch.object(
            AirbyteK8SOperatorCharm, "reconcile", lambda charm: charm.postgresql_connectors.reconcile()
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.ctx = testing.Context(AirbyteK8SOperatorCharm)

    def run_changed(self, state, relation):
        """Run relation-changed for a relation.

        Args:
            state: the input state.
            relation: the relation that changed.

        Returns:
            The output state.
        """
        return self.ctx.run(self.ctx.on.relation_changed(relation), state)

    def test_databag_written(self):
        """The leader requests the prefix and secrets once a config entry exists."""
        secret = user_secret()
        relation = testing.Relation("postgresql-source", remote_app_name=PG_APP)
        out = self.ctx.run(self.ctx.on.relation_created(relation), make_state(relation, secrets=[secret]))
        databag = out.get_relation(relation.id).local_app_data
        self.assertEqual(databag["database"], "dbaas*")
        self.assertEqual(json.loads(databag["requested-secrets"]), ["username", "password", "tls", "tls-ca"])
        self.assertEqual(databag["extra-user-roles"], "charmed_read")

    def test_destination_databag_has_no_extra_roles(self):
        """Destinations keep the default database owner access needed to create tables."""
        relation = testing.Relation("postgresql-destination", remote_app_name=PG_APP)
        entry = {"database_prefix": "dbaas*", "schema": "public"}
        config = {"postgresql-destination-config": yaml.safe_dump({PG_APP: entry})}
        out = self.ctx.run(self.ctx.on.relation_created(relation), make_state(relation, config=config))
        databag = out.get_relation(relation.id).local_app_data
        self.assertEqual(databag["database"], "dbaas*")
        self.assertNotIn("extra-user-roles", databag)

    def test_destination_schema_required(self):
        """A destination entry without a schema is invalid and requests nothing."""
        relation = testing.Relation("postgresql-destination", remote_app_name=PG_APP)
        for entry in ({"database_prefix": "dbaas*"}, {"database_prefix": "dbaas*", "schema": ""}):
            config = {"postgresql-destination-config": yaml.safe_dump({PG_APP: entry})}
            out = self.ctx.run(self.ctx.on.relation_created(relation), make_state(relation, config=config))
            self.assertNotIn("database", out.get_relation(relation.id).local_app_data)

    def test_databag_not_written_without_config(self):
        """No databag is written for a relation without a config entry."""
        relation = testing.Relation("postgresql-source", remote_app_name="other-app")
        out = self.ctx.run(self.ctx.on.relation_created(relation), make_state(relation))
        self.assertNotIn("database", out.get_relation(relation.id).local_app_data)

    def test_invalid_config_ignored(self):
        """Invalid entries create nothing and leave the charm status untouched."""
        secret = user_secret()
        for config in (
            source_config(database_prefix="dbaas"),
            source_config(unknown="field"),
            source_config(name="{unknown}"),
            source_config(schemas=[]),
            {"postgresql-source-config": yaml.safe_dump({PG_APP: {"database_prefix": "dbaas*"}})},
            {"postgresql-source-config": "not: [valid"},
        ):
            relation = pg_relation(secret)
            out = self.run_changed(make_state(relation, secrets=[secret], config=config), relation)
            self.assertEqual(tracked_state(out), {})
            self.assertEqual(out.unit_status, testing.UnknownStatus())
        self.assertEqual(self.airbyte.calls, [])

    def test_creates_source_per_database(self):
        """One source is created per matched database with multi-host and preferSecondary."""
        secret = user_secret()
        relation = pg_relation(secret)
        out = self.run_changed(make_state(relation, secrets=[secret]), relation)

        tracked = tracked_state(out)
        self.assertEqual(set(tracked), {f"source:{PG_APP}:dbaas_a", f"source:{PG_APP}:dbaas_b"})
        record = tracked[f"source:{PG_APP}:dbaas_a"]
        connector = self.airbyte.connectors[record["id"]]
        self.assertEqual(connector["name"], f"{PG_APP}-dbaas_a")
        configuration = connector["configuration"]
        self.assertEqual(configuration["sourceType"], "postgres")
        self.assertEqual(configuration["host"], f"{PRIMARY},{REPLICAS.rsplit(':', 1)[0]}")
        self.assertEqual(configuration["port"], 5432)
        self.assertEqual(configuration["jdbc_url_params"], "targetServerType=preferSecondary")
        self.assertEqual(configuration["password"], "pw")

    def test_creates_destination_with_primary(self):
        """Destinations target the primary and use the configured schema."""
        secret = user_secret()
        relation = pg_relation(secret, endpoint="postgresql-destination", databases="wh_1")
        config = {
            "postgresql-destination-config": yaml.safe_dump(
                {PG_APP: {"database_prefix": "wh*", "schema": "raw", "jdbc_url_params": "targetServerType=any"}}
            )
        }
        out = self.run_changed(make_state(relation, secrets=[secret], config=config), relation)

        record = tracked_state(out)[f"destination:{PG_APP}:wh_1"]
        configuration = self.airbyte.connectors[record["id"]]["configuration"]
        self.assertEqual(configuration["destinationType"], "postgres")
        self.assertEqual(configuration["schema"], "raw")
        self.assertEqual(configuration["jdbc_url_params"], "targetServerType=primary")

    def test_no_update_when_unchanged(self):
        """A second reconcile without changes makes no write calls."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        out = self.run_changed(make_state(relation, secrets=[secret]), relation)
        self.airbyte.calls.clear()

        self.run_changed(make_state(relation, secrets=[secret], tracked=tracked_state(out)), relation)
        self.assertEqual(self.airbyte.calls, [])

    def test_password_rotation_updates(self):
        """A rotated password is pushed to the existing connector."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        connector_id = tracked[f"source:{PG_APP}:dbaas_a"]["id"]

        rotated = user_secret(password="new-pw")  # nosec B106
        rotated_relation = pg_relation(rotated, databases="dbaas_a")
        state = make_state(rotated_relation, secrets=[rotated], tracked=tracked)
        self.ctx.run(self.ctx.on.secret_changed(rotated), state)

        self.assertIn(("update", "source", connector_id), self.airbyte.calls)
        self.assertEqual(self.airbyte.connectors[connector_id]["configuration"]["password"], "new-pw")

    def test_workspace_change_not_applied(self):
        """A workspace change leaves the connector in its workspace and logs a warning."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        connector_id = tracked[f"source:{PG_APP}:dbaas_a"]["id"]
        self.airbyte.calls.clear()

        state = make_state(relation, secrets=[secret], config=source_config(workspace="team"), tracked=tracked)
        with self.assertLogs("relations.postgresql_connectors", level="WARNING") as logs:
            out = self.run_changed(state, relation)

        self.assertEqual(self.airbyte.calls, [])
        self.assertEqual(self.airbyte.connectors[connector_id]["workspaceId"], "ws-1")
        self.assertEqual(tracked_state(out)[f"source:{PG_APP}:dbaas_a"]["id"], connector_id)
        self.assertTrue(any("cannot be moved" in line for line in logs.output))

    def test_workspace_change_applied_after_manual_delete(self):
        """Deleting the connector after a workspace change recreates it in the new workspace."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        del self.airbyte.connectors[tracked[f"source:{PG_APP}:dbaas_a"]["id"]]

        state = make_state(relation, secrets=[secret], config=source_config(workspace="team"), tracked=tracked)
        out = self.run_changed(state, relation)
        new_id = tracked_state(out)[f"source:{PG_APP}:dbaas_a"]["id"]
        self.assertEqual(self.airbyte.connectors[new_id]["workspaceId"], "ws-team")

    def test_recreates_deleted_connector(self):
        """A managed connector deleted in Airbyte is recreated."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        old_id = tracked[f"source:{PG_APP}:dbaas_a"]["id"]
        del self.airbyte.connectors[old_id]

        out = self.run_changed(make_state(relation, secrets=[secret], tracked=tracked), relation)
        new_id = tracked_state(out)[f"source:{PG_APP}:dbaas_a"]["id"]
        self.assertNotEqual(new_id, old_id)
        self.assertIn(new_id, self.airbyte.connectors)

    def test_relation_removed_orphans(self):
        """Removing the relation orphans connectors without deleting them."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))

        state = make_state(relation, secrets=[secret], tracked=tracked)
        out = self.ctx.run(self.ctx.on.relation_broken(relation), state)

        record = tracked_state(out)[f"source:{PG_APP}:dbaas_a"]
        self.assertTrue(record["orphaned"])
        self.assertIn(record["id"], self.airbyte.connectors)

    def test_malformed_relation_skipped(self):
        """A relation with malformed data is skipped while other relations still reconcile."""
        good_secret = user_secret()
        good = pg_relation(good_secret, databases="dbaas_a")
        bad_secret = testing.Secret(tracked_content={"password": "pw"}, latest_content={"password": "pw"})  # nosec
        bad = pg_relation(bad_secret, databases="dbaas_a", app="other-db")
        entry = {"database_prefix": "dbaas*", "schemas": ["public"]}
        config = {"postgresql-source-config": yaml.safe_dump({PG_APP: entry, "other-db": entry})}
        state = make_state(good, bad, secrets=[good_secret, bad_secret], config=config)

        with self.assertLogs("relations.postgresql_connectors", level="ERROR") as logs:
            out = self.run_changed(state, bad)

        self.assertEqual(set(tracked_state(out)), {f"source:{PG_APP}:dbaas_a"})
        self.assertTrue(any("other-db" in line and "malformed" in line for line in logs.output))

    def test_malformed_relation_keeps_connectors(self):
        """Connectors of a relation whose data becomes malformed are not orphaned."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        self.airbyte.calls.clear()

        broken = dataclasses.replace(relation, remote_app_data={**relation.remote_app_data, "endpoints": "no-port"})
        out = self.run_changed(make_state(broken, secrets=[secret], tracked=tracked), broken)

        self.assertEqual(tracked_state(out), tracked)
        self.assertEqual(self.airbyte.calls, [])

    def test_orphan_deleted_manually_untracked(self):
        """An orphaned connector deleted by a user is no longer tracked."""
        tracked = {
            f"source:{PG_APP}:dbaas_a": {
                "type": "source",
                "app": PG_APP,
                "database": "dbaas_a",
                "id": "gone",
                "hash": "x",
                "orphaned": True,
            }
        }
        out = self.ctx.run(self.ctx.on.config_changed(), make_state(tracked=tracked))
        self.assertEqual(tracked_state(out), {})

    def test_readopts_orphan(self):
        """Re-relating re-adopts an orphaned connector with the same ID."""
        secret = user_secret()
        relation = pg_relation(secret, databases="dbaas_a")
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        key = f"source:{PG_APP}:dbaas_a"
        connector_id = tracked[key]["id"]
        tracked[key]["orphaned"] = True

        new_relation = pg_relation(secret, databases="dbaas_a")
        out = self.run_changed(make_state(new_relation, secrets=[secret], tracked=tracked), new_relation)
        record = tracked_state(out)[key]
        self.assertEqual(record["id"], connector_id)
        self.assertFalse(record["orphaned"])

    def test_unhealthy_airbyte_skips(self):
        """Nothing is created while Airbyte is not healthy."""
        self.airbyte.healthy = False
        secret = user_secret()
        relation = pg_relation(secret)
        out = self.run_changed(make_state(relation, secrets=[secret]), relation)
        self.assertEqual(tracked_state(out), {})
        self.assertEqual(self.airbyte.calls, [])

    def test_non_leader_does_nothing(self):
        """Only the leader reconciles connectors."""
        secret = user_secret()
        relation = pg_relation(secret)
        out = self.run_changed(make_state(relation, secrets=[secret], leader=False), relation)
        self.assertNotIn("database", out.get_relation(relation.id).local_app_data)
        self.assertEqual(self.airbyte.calls, [])

    def test_action_lists_connectors(self):
        """The action returns live details, filtered by type, skipping deleted ones."""
        secret = user_secret()
        relation = pg_relation(secret)
        tracked = tracked_state(self.run_changed(make_state(relation, secrets=[secret]), relation))
        tracked["destination:wh:wh_1"] = {
            "type": "destination",
            "app": "wh",
            "database": "wh_1",
            "id": "destination-9",
            "hash": "x",
            "orphaned": False,
        }
        deleted_id = tracked[f"source:{PG_APP}:dbaas_b"]["id"]
        del self.airbyte.connectors[deleted_id]

        self.ctx.run(
            self.ctx.on.action("list-managed-connectors", params={"type": "source"}), make_state(tracked=tracked)
        )
        connectors = json.loads(dict(self.ctx.action_results or {})["connectors"])
        self.assertEqual(
            connectors,
            [
                {
                    "type": "source",
                    "id": tracked[f"source:{PG_APP}:dbaas_a"]["id"],
                    "name": f"{PG_APP}-dbaas_a",
                    "database": "dbaas_a",
                    "app": PG_APP,
                    "orphaned": False,
                }
            ],
        )

    def test_action_fails_when_unreachable(self):
        """The action fails when Airbyte is unreachable."""
        tracked = {
            "source:a:db": {"type": "source", "app": "a", "database": "db", "id": "s", "hash": "x", "orphaned": False}
        }
        self.airbyte.unreachable = True
        with self.assertRaises(testing.ActionFailed):
            self.ctx.run(self.ctx.on.action("list-managed-connectors"), make_state(tracked=tracked))
