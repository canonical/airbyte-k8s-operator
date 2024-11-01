#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration test helpers."""

import logging
import time
from pathlib import Path

import requests
import yaml
from pytest_operator.plugin import OpsTest
from temporal_client.activities import say_hello
from temporal_client.workflows import SayHello
from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME_AIRBYTE_SERVER = METADATA["name"]
APP_NAME_TEMPORAL_SERVER = "temporal-k8s"
APP_NAME_TEMPORAL_ADMIN = "temporal-admin-k8s"
APP_NAME_TEMPORAL_UI = "temporal-ui-k8s"

GET_HEADERS = {"accept": "application/json"}
POST_HEADERS = {"accept": "application/json", "content-type": "application/json"}


async def run_sample_workflow(ops_test: OpsTest):
    """Connect a client and runs a basic Temporal workflow.

    Args:
        ops_test: PyTest object.
    """
    url = await get_application_url(ops_test, application=APP_NAME_TEMPORAL_SERVER, port=7233)
    logger.info("running workflow on app address: %s", url)

    client = await Client.connect(url)

    # Run a worker for the workflow
    async with Worker(client, task_queue="my-task-queue", workflows=[SayHello], activities=[say_hello]):
        name = "Jean-luc"
        result = await client.execute_workflow(SayHello.run, name, id="my-workflow-id", task_queue="my-task-queue")
        logger.info(f"result: {result}")
        assert result == f"Hello, {name}!"


async def create_default_namespace(ops_test: OpsTest):
    """Create default namespace on Temporal server using tctl.

    Args:
        ops_test: PyTest object.
    """
    # Register default namespace from admin charm.
    action = (
        await ops_test.model.applications[APP_NAME_TEMPORAL_ADMIN]
        .units[0]
        .run_action("tctl", args="--ns default namespace register -rd 3")
    )
    result = (await action.wait()).results
    logger.info(f"tctl result: {result}")
    assert "result" in result and result["result"] == "command succeeded"


async def get_application_url(ops_test: OpsTest, application, port):
    """Return application URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        port: Port number of the URL.

    Returns:
        Application URL of the form {address}:{port}
    """
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][application].public_address
    return f"{address}:{port}"


async def get_unit_url(ops_test: OpsTest, application, unit, port, protocol="http"):
    """Return unit URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        unit: Number of the unit.
        port: Port number of the URL.
        protocol: Transfer protocol (default: http).

    Returns:
        Unit URL of the form {protocol}://{address}:{port}
    """
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][application]["units"][f"{application}/{unit}"]["address"]
    return f"{protocol}://{address}:{port}"


async def perform_temporal_integrations(ops_test: OpsTest):
    """Integrate Temporal charm with postgresql, admin and ui charms.

    Args:
        ops_test: PyTest object.
    """
    await ops_test.model.integrate(f"{APP_NAME_TEMPORAL_SERVER}:db", "postgresql-k8s:database")
    await ops_test.model.integrate(f"{APP_NAME_TEMPORAL_SERVER}:visibility", "postgresql-k8s:database")
    await ops_test.model.integrate(f"{APP_NAME_TEMPORAL_SERVER}:admin", f"{APP_NAME_TEMPORAL_ADMIN}:admin")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME_TEMPORAL_SERVER, "postgresql-k8s"], status="active", raise_on_blocked=False, timeout=180
    )

    assert ops_test.model.applications[APP_NAME_TEMPORAL_SERVER].units[0].workload_status == "active"


async def perform_airbyte_integrations(ops_test: OpsTest):
    """Perform Airbyte charm integrations.

    Args:
        ops_test: PyTest object.
    """
    await ops_test.model.integrate(APP_NAME_AIRBYTE_SERVER, "postgresql-k8s")
    await ops_test.model.integrate(APP_NAME_AIRBYTE_SERVER, "minio")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME_AIRBYTE_SERVER, "postgresql-k8s", "minio"],
        status="active",
        raise_on_blocked=False,
        wait_for_active=True,
        idle_period=60,
        timeout=300,
    )

    assert ops_test.model.applications[APP_NAME_AIRBYTE_SERVER].units[0].workload_status == "active"


def get_airbyte_workspace_id(api_url):
    """Get Airbyte default workspace ID.

    Args:
        api_url: Airbyte API base URL.

    Returns:
        Airbyte workspace ID.
    """
    url = f"{api_url}/api/public/v1/workspaces?includeDeleted=false&limit=20&offset=0"
    logger.info("fetching Airbyte workspace ID")
    response = requests.get(url, headers=GET_HEADERS, timeout=300)

    assert response.status_code == 200
    return response.json().get("data")[0]["workspaceId"]


def create_airbyte_source(api_url, workspace_id):
    """Create Airbyte sample source.

    Args:
        api_url: Airbyte API base URL.
        workspace_id: default workspace ID.

    Returns:
        Created source ID.
    """
    url = f"{api_url}/api/public/v1/sources"
    payload = {
        "configuration": {"sourceType": "pokeapi", "pokemon_name": "pikachu"},
        "name": "API Test",
        "workspaceId": workspace_id,
    }

    logger.info("creating Airbyte source")
    response = requests.post(url, json=payload, headers=POST_HEADERS, timeout=300)
    logger.info(response.json())

    assert response.status_code == 200
    return response.json().get("sourceId")


def create_airbyte_destination(api_url, model_name, workspace_id, db_password):
    """Create Airbyte sample destination.

    Args:
        api_url: Airbyte API base URL.
        model_name: name of the juju model.
        workspace_id: default workspace ID.
        db_password: database password.

    Returns:
        Created destination ID.
    """
    url = f"{api_url}/api/public/v1/destinations"
    payload = {
        "configuration": {
            "destinationType": "postgres",
            "port": 5432,
            "schema": "pokeapi",
            "ssl_mode": {"mode": "disable"},
            "tunnel_method": {"tunnel_method": "NO_TUNNEL"},
            "host": f"postgresql-k8s-primary.{model_name}.svc.cluster.local",
            "database": "airbyte-k8s_db",
            "username": "operator",
            "password": db_password,
        },
        "workspaceId": workspace_id,
        "name": "Postgres",
    }

    logger.info("creating Airbyte destination")
    response = requests.post(url, json=payload, headers=POST_HEADERS, timeout=300)
    logger.info(response.json())

    assert response.status_code == 200
    return response.json().get("destinationId")


def create_airbyte_connection(api_url, source_id, destination_id):
    """Create Airbyte connection.

    Args:
        api_url: Airbyte API base URL.
        source_id: Airbyte source ID.
        destination_id: Airbyte destination ID.

    Returns:
        Created connection ID.
    """
    url = f"{api_url}/api/public/v1/connections"
    payload = {
        "schedule": {"scheduleType": "manual"},
        "dataResidency": "auto",
        "namespaceDefinition": "destination",
        "namespaceFormat": None,
        "nonBreakingSchemaUpdatesBehavior": "ignore",
        "sourceId": source_id,
        "destinationId": destination_id,
    }

    logger.info("creating Airbyte connection")
    response = requests.post(url, json=payload, headers=POST_HEADERS, timeout=900)
    logger.info(response.json())

    assert response.status_code == 200
    return response.json().get("connectionId")


def trigger_airbyte_connection(api_url, connection_id):
    """Trigger Airbyte connection.

    Args:
        api_url: Airbyte API base URL.
        connection_id: Airbyte connection ID.

    Returns:
        Created job ID.
    """
    url = f"{api_url}/api/public/v1/jobs"
    payload = {"jobType": "sync", "connectionId": connection_id}
    logger.info("triggering Airbyte connection")
    response = requests.post(url, json=payload, headers=POST_HEADERS, timeout=300)
    logger.info(response.json())

    assert response.status_code == 200
    return response.json().get("jobId")


def check_airbyte_job_status(api_url, job_id):
    """Get Airbyte sync job status.

    Args:
        api_url: Airbyte API base URL.
        job_id: Sync job ID.

    Returns:
        Job status.
    """
    url = f"{api_url}/api/public/v1/jobs/{job_id}"
    logger.info("fetching Airbyte job status")
    response = requests.get(url, headers=GET_HEADERS, timeout=120)
    logger.info(response.json())

    return response.json().get("status")


def cancel_airbyte_job(api_url, job_id):
    """Cancel Airbyte sync job.

    Args:
        api_url: Airbyte API base URL.
        job_id: Sync job ID.

    Returns:
        Job status.
    """
    url = f"{api_url}/api/public/v1/jobs/{job_id}"
    logger.info("cancelling Airbyte job")
    response = requests.delete(url, headers=GET_HEADERS, timeout=120)
    logger.info(response.json())

    return response.json().get("status")


async def get_db_password(ops_test):
    """Get PostgreSQL DB admin password.

    Args:
        ops_test: PyTest object.

    Returns:
        PostgreSQL DB admin password.
    """
    postgresql_unit = ops_test.model.applications["postgresql-k8s"].units[0]
    for i in range(10):
        action = await postgresql_unit.run_action("get-password")
        result = await action.wait()
        logger.info(f"attempt {i} -> action result {result.status} {result.results}")
        if "password" in result.results:
            return result.results["password"]
        time.sleep(2)


async def run_test_sync_job(ops_test):
    """Run test Airbyte connection.

    Args:
        ops_test: PyTest object.
    """
    # Create connection
    api_url = await get_unit_url(ops_test, application=APP_NAME_AIRBYTE_SERVER, unit=0, port=8001)
    logger.info("curling app address: %s", api_url)
    workspace_id = get_airbyte_workspace_id(api_url)
    db_password = await get_db_password(ops_test)
    assert db_password

    # Create Source
    source_id = create_airbyte_source(api_url, workspace_id)

    # Create destination
    destination_id = create_airbyte_destination(api_url, ops_test.model.name, workspace_id, db_password)

    # Create connection
    connection_id = create_airbyte_connection(api_url, source_id, destination_id)

    # Trigger sync job
    for i in range(2):
        logger.info(f"attempt {i + 1} to trigger new job")
        job_id = trigger_airbyte_connection(api_url, connection_id)

        # Wait until job is successful
        job_successful = False
        for j in range(7):
            logger.info(f"job {i + 1} attempt {j + 1}: getting job status")
            status = check_airbyte_job_status(api_url, job_id)

            if status == "failed":
                break

            if status == "succeeded":
                logger.info(f"job {i + 1} attempt {j + 1}: job successful!")
                job_successful = True
                break

            logger.info(f"job {i + 1} attempt {j + 1}: job still running, retrying in 10 seconds")
            time.sleep(10)

        if job_successful:
            break

        cancel_airbyte_job(api_url, job_id)

    assert job_successful
