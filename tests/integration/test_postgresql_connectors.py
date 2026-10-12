#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the postgresql-source and postgresql-destination relations.

The tests run in order and build on each other, like the Trino-PostgreSQL relation suite.
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import helpers
import jubilant
import pytest
import requests
import yaml

logger = logging.getLogger(__name__)

APP = helpers.APP_NAME_AIRBYTE_SERVER
PG = "pg-connectors"
PG16_CHANNEL = "16/edge"
DATA_INTEGRATOR_CHANNEL = "latest/edge"
TLS_NAME = "self-signed-certificates"
TLS_CHANNEL = "latest/edge"

SOURCE_ENDPOINT = f"{APP}:postgresql-source"
DESTINATION_ENDPOINT = f"{APP}:postgresql-destination"
PG_ENDPOINT = f"{PG}:database"
SOURCE_CONFIG = "postgresql-source-config"
DESTINATION_CONFIG = "postgresql-destination-config"

# Data shared between the ordered tests.
STATE: dict = {}


def deploy_database(juju: jubilant.Juju, database: str) -> None:
    """Create a database on the PG16 app through a data-integrator.

    PostgreSQL prefix matching only discovers existing databases, so they are
    created by a data-integrator first.

    Args:
        juju: Jubilant object.
        database: name of the database to create.
    """
    name = f"di-{database.replace('_', '-')}"
    juju.deploy("data-integrator", name, channel=DATA_INTEGRATOR_CHANNEL, config={"database-name": database})
    juju.integrate(name, PG_ENDPOINT)
    helpers.wait_for_all_active(juju, [PG, name], timeout=15 * 60)


def set_config(juju: jubilant.Juju, option: str, entries: dict) -> None:
    """Set a postgresql-*-config option and wait for the charm to settle.

    Args:
        juju: Jubilant object.
        option: the config option name.
        entries: config entries keyed by PostgreSQL application name.
    """
    juju.config(APP, {option: yaml.safe_dump(entries)})
    wait_for_idle(juju)


def wait_for_idle(juju: jubilant.Juju) -> None:
    """Wait for Airbyte and PostgreSQL to be idle, with Airbyte active.

    Args:
        juju: Jubilant object.
    """
    juju.wait(lambda status: jubilant.all_agents_idle(status, APP, PG), timeout=15 * 60)
    helpers.wait_for_all_active(juju, [APP], timeout=15 * 60)


def list_managed(juju: jubilant.Juju, connector_type: Optional[str] = None) -> list[dict]:
    """Run the list-managed-connectors action.

    Args:
        juju: Jubilant object.
        connector_type: optional type filter.

    Returns:
        The managed connectors.
    """
    params = {"type": connector_type} if connector_type else {}
    task = juju.run(f"{APP}/0", "list-managed-connectors", params, wait=5 * 60)
    return json.loads(task.results["connectors"])


def wait_for(description: str, check: Callable, timeout: float = 15 * 60, interval: float = 20):
    """Poll until check returns a truthy value.

    Args:
        description: what is being waited for, for error messages.
        check: callable returning a truthy value when done.
        timeout: maximum seconds to wait.
        interval: seconds between attempts.

    Returns:
        The truthy value returned by check.

    Raises:
        AssertionError: if check never returns a truthy value in time.
    """
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            result = check()
            if result:
                return result
        except Exception as err:  # pylint: disable=broad-exception-caught
            last_error = err
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for {description}; last error: {last_error}")


def wait_for_managed(juju: jubilant.Juju, description: str, predicate: Callable[[list[dict]], bool]) -> list[dict]:
    """Wait until the managed connectors satisfy a predicate.

    Args:
        juju: Jubilant object.
        description: what is being waited for, for error messages.
        predicate: callable receiving the managed connectors.

    Returns:
        The managed connectors.
    """

    def check():
        """Return the connectors if they satisfy the predicate.

        Returns:
            The connectors, or None.
        """
        connectors = list_managed(juju)
        logger.info("managed connectors: %s", connectors)
        return connectors if predicate(connectors) else None

    return wait_for(description, check)


def by_database(connectors: list[dict], connector_type: str) -> dict[str, dict]:
    """Index connectors of a type by database.

    Args:
        connectors: managed connectors.
        connector_type: "source" or "destination".

    Returns:
        Connectors keyed by database.
    """
    return {c["database"]: c for c in connectors if c["type"] == connector_type}


def api_url(juju: jubilant.Juju) -> str:
    """Return the Airbyte API base URL.

    Args:
        juju: Jubilant object.

    Returns:
        The base URL.
    """
    return helpers.get_unit_url(juju, APP, 0, helpers.INTERNAL_API_PORT)


def get_connector(juju: jubilant.Juju, connector_type: str, connector_id: str) -> dict:
    """Fetch a source or destination from the Airbyte API.

    Args:
        juju: Jubilant object.
        connector_type: "source" or "destination".
        connector_id: the connector ID.

    Returns:
        The connector.
    """
    url = f"{api_url(juju)}/api/public/v1/{connector_type}s/{connector_id}"
    response = requests.get(url, headers=helpers.GET_HEADERS, timeout=60)
    assert response.status_code == 200, f"GET {url} returned {response.status_code}: {response.text}"
    return response.json()


def create_connection(juju: jubilant.Juju, source_id: str, destination_id: str, namespace_format: str) -> str:
    """Create a manual connection writing into a custom namespace.

    Args:
        juju: Jubilant object.
        source_id: the source ID.
        destination_id: the destination ID.
        namespace_format: the destination namespace.

    Returns:
        The connection ID.
    """
    payload = {
        "schedule": {"scheduleType": "manual"},
        "namespaceDefinition": "custom_format",
        "namespaceFormat": namespace_format,
        "nonBreakingSchemaUpdatesBehavior": "ignore",
        "sourceId": source_id,
        "destinationId": destination_id,
    }
    url = f"{api_url(juju)}/api/public/v1/connections"
    response = helpers.post_with_retry(url, payload, attempts=10, timeout=600)
    return response.json()["connectionId"]


@pytest.fixture(scope="module")
def juju(k8s_juju: jubilant.Juju, charm: Path, rock_resources: dict) -> jubilant.Juju:
    """Deploy Airbyte with its stack, plus a PG16 app with a database to match.

    Args:
        k8s_juju: Jubilant object for the K8s model.
        charm: Path to the local charm package.
        rock_resources: Local rock resource image map.

    Returns:
        The Jubilant object.
    """
    helpers.deploy_full_stack(k8s_juju, charm, rock_resources)
    k8s_juju.deploy("postgresql-k8s", PG, channel=PG16_CHANNEL, trust=True)
    helpers.wait_for_apps_status(k8s_juju, {PG: "active"}, timeout=20 * 60)
    deploy_database(k8s_juju, "testdb_a")
    return k8s_juju


def test_relation_without_config(juju: jubilant.Juju):
    """A relation without a config entry creates nothing and keeps Airbyte active."""
    juju.integrate(SOURCE_ENDPOINT, PG_ENDPOINT)
    wait_for_idle(juju)
    assert list_managed(juju) == []


def test_invalid_config(juju: jubilant.Juju):
    """A database prefix without `*` is rejected without blocking the charm."""
    set_config(juju, SOURCE_CONFIG, {PG: {"database_prefix": "testdb"}})
    assert list_managed(juju) == []


def test_source_created(juju: jubilant.Juju):
    """A valid config creates a source using multi-host JDBC and preferSecondary."""
    set_config(
        juju,
        SOURCE_CONFIG,
        {PG: {"database_prefix": "testdb*", "jdbc_url_params": "connectTimeout=10&targetServerType=any"}},
    )
    connectors = wait_for_managed(juju, "source for testdb_a", lambda c: "testdb_a" in by_database(c, "source"))
    source = by_database(connectors, "source")["testdb_a"]
    assert source["name"] == f"{PG}-testdb_a"
    assert source["app"] == PG
    assert source["orphaned"] is False

    configuration = get_connector(juju, "source", source["id"])["configuration"]
    assert f"{PG}-primary" in configuration["host"]
    assert configuration["jdbc_url_params"] == "targetServerType=preferSecondary&connectTimeout=10"
    assert configuration["ssl_mode"]["mode"] == "disable"
    STATE["source_a"] = source["id"]


def test_new_database_auto_added(juju: jubilant.Juju):
    """A database created later that matches the prefix gets its own source."""
    deploy_database(juju, "testdb_b")
    connectors = wait_for_managed(juju, "source for testdb_b", lambda c: "testdb_b" in by_database(c, "source"))
    sources = by_database(connectors, "source")
    assert sources["testdb_a"]["id"] == STATE["source_a"]
    STATE["source_b"] = sources["testdb_b"]["id"]


def test_destination_created(juju: jubilant.Juju):
    """The destination endpoint creates a destination targeting the primary."""
    juju.config(APP, {DESTINATION_CONFIG: yaml.safe_dump({PG: {"database_prefix": "testdb_a*"}})})
    juju.integrate(DESTINATION_ENDPOINT, PG_ENDPOINT)
    wait_for_idle(juju)

    connectors = wait_for_managed(juju, "destination", lambda c: "testdb_a" in by_database(c, "destination"))
    destination = by_database(connectors, "destination")["testdb_a"]
    configuration = get_connector(juju, "destination", destination["id"])["configuration"]
    assert configuration["jdbc_url_params"] == "targetServerType=primary"
    assert f"{PG}-primary" in configuration["host"]
    STATE["destination"] = destination["id"]


def test_action_type_filter(juju: jubilant.Juju):
    """The action filters by connector type."""
    sources = list_managed(juju, "source")
    destinations = list_managed(juju, "destination")
    assert {c["type"] for c in sources} == {"source"}
    assert {c["id"] for c in sources} == {STATE["source_a"], STATE["source_b"]}
    assert [c["id"] for c in destinations] == [STATE["destination"]]


def test_sync_into_managed_destination(juju: jubilant.Juju):
    """A manual source syncs into the managed destination."""
    url = api_url(juju)
    workspace_id = helpers.get_airbyte_workspace_id(url)
    STATE["manual_source"] = helpers.create_airbyte_source(url, workspace_id)
    connection_id = create_connection(juju, STATE["manual_source"], STATE["destination"], "public")
    helpers.sync_connection(juju, connection_id)


def test_sync_from_managed_source(juju: jubilant.Juju):
    """The managed source reads the synced table and loads it into the managed destination."""
    connection_id = create_connection(juju, STATE["source_a"], STATE["destination"], "copy")
    helpers.sync_connection(juju, connection_id)
    STATE["source_connection"] = connection_id


def test_pg_scaling_updates_hosts(juju: jubilant.Juju):
    """Scaling PostgreSQL adds the replicas endpoint to the source hosts."""
    juju.add_unit(PG, num_units=1)
    helpers.wait_for_all_active(juju, [PG], timeout=20 * 60)

    def has_replicas():
        """Return whether the source host includes the replicas service.

        Returns:
            True when the replicas service is in the host list.
        """
        host = get_connector(juju, "source", STATE["source_a"])["configuration"]["host"]
        logger.info("source host: %s", host)
        return f"{PG}-replicas" in host and f"{PG}-primary" in host

    wait_for("replicas endpoint in source host", has_replicas)
    helpers.sync_connection(juju, STATE["source_connection"])


def test_deleted_connector_recreated(juju: jubilant.Juju):
    """A managed source deleted in Airbyte while still wanted is recreated."""
    url = f"{api_url(juju)}/api/public/v1/sources/{STATE['source_b']}"
    response = requests.delete(url, headers=helpers.GET_HEADERS, timeout=60)
    assert response.status_code in (200, 204), response.text

    def recreated(connectors):
        """Return whether testdb_b has a new source.

        Args:
            connectors: managed connectors.

        Returns:
            True once testdb_b has a source with a new ID.
        """
        source = by_database(connectors, "source").get("testdb_b")
        return source is not None and source["id"] != STATE["source_b"]

    connectors = wait_for_managed(juju, "recreated source for testdb_b", recreated)
    STATE["source_b"] = by_database(connectors, "source")["testdb_b"]["id"]


def test_remove_relation_orphans(juju: jubilant.Juju):
    """Removing the source relation keeps the sources, flagged as orphaned."""
    juju.remove_relation(SOURCE_ENDPOINT, PG_ENDPOINT)
    wait_for_idle(juju)

    connectors = wait_for_managed(
        juju,
        "orphaned sources",
        lambda c: len(by_database(c, "source")) == 2 and all(s["orphaned"] for s in by_database(c, "source").values()),
    )
    assert by_database(connectors, "source")["testdb_a"]["id"] == STATE["source_a"]
    assert not by_database(connectors, "destination")["testdb_a"]["orphaned"]


def test_readd_relation_readopts(juju: jubilant.Juju):
    """Re-adding the relation re-adopts the orphaned sources with new credentials."""
    juju.integrate(SOURCE_ENDPOINT, PG_ENDPOINT)
    wait_for_idle(juju)

    connectors = wait_for_managed(
        juju,
        "re-adopted sources",
        lambda c: len(by_database(c, "source")) == 2
        and not any(s["orphaned"] for s in by_database(c, "source").values()),
    )
    sources = by_database(connectors, "source")
    assert sources["testdb_a"]["id"] == STATE["source_a"]
    assert sources["testdb_b"]["id"] == STATE["source_b"]
    # The new relation has a new PostgreSQL user, so this proves the credentials were updated.
    helpers.sync_connection(juju, STATE["source_connection"])


def test_manual_connector_untouched(juju: jubilant.Juju):
    """Manually created connectors are not managed or modified."""
    ids = {c["id"] for c in list_managed(juju)}
    assert STATE["manual_source"] not in ids
    assert get_connector(juju, "source", STATE["manual_source"])["name"] == "API Test"


def test_tls(juju: jubilant.Juju):
    """Connectors switch to verify-ca when PostgreSQL enables TLS, and syncs still succeed."""
    juju.deploy(TLS_NAME, channel=TLS_CHANNEL)
    helpers.wait_for_all_active(juju, [TLS_NAME], timeout=10 * 60)
    juju.integrate(f"{PG}:client-certificates", f"{TLS_NAME}:certificates")
    helpers.wait_for_all_active(juju, [PG, TLS_NAME], timeout=20 * 60)

    def uses_tls():
        """Return whether both managed connectors verify the CA.

        Returns:
            True once source and destination use verify-ca.
        """
        source = get_connector(juju, "source", STATE["source_a"])["configuration"]
        destination = get_connector(juju, "destination", STATE["destination"])["configuration"]
        logger.info("ssl modes: %s, %s", source["ssl_mode"]["mode"], destination["ssl_mode"]["mode"])
        return source["ssl_mode"]["mode"] == "verify-ca" and destination["ssl_mode"]["mode"] == "verify-ca"

    wait_for("verify-ca on managed connectors", uses_tls)
    helpers.sync_connection(juju, STATE["source_connection"])
