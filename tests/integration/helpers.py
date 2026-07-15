#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration test helpers."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence

import jubilant
import requests
import yaml
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

POSTGRES_NAME = "postgresql-k8s"
POSTGRES_CHANNEL = "14/stable"
POSTGRES_REVISION = 381
MINIO_NAME = "minio"
MINIO_CHANNEL = "1.10/stable"
TEMPORAL_CHANNEL = "1.23/stable"
TEMPORAL_BASE = "ubuntu@24.04"

INTERNAL_API_PORT = 8001
TEMPORAL_PORT = 7233

GET_HEADERS = {"accept": "application/json"}
POST_HEADERS = {"accept": "application/json", "content-type": "application/json"}


def model_short_name(model_name: str) -> str:
    """Return model name without the controller prefix.

    Args:
        model_name: Full model name, possibly controller-prefixed.

    Returns:
        Model name without the controller prefix.
    """
    if ":" in model_name:
        return model_name.split(":", maxsplit=1)[1]
    return model_name


def _app_status_current(status: jubilant.Status, app_name: str) -> str:
    """Read workload status for an app, returning empty string if app is absent.

    Args:
        status: Jubilant status object.
        app_name: Application name.

    Returns:
        The app's current workload status, or "" if the app is absent.
    """
    app = status.apps.get(app_name)
    if not app:
        return ""
    return app.app_status.current


def wait_for_apps_status(
    juju: jubilant.Juju,
    expected_by_app: Mapping[str, str | Sequence[str]],
    *,
    timeout: float,
    raise_on_error: bool = True,
) -> None:
    """Wait until every app reaches one of its expected workload statuses.

    Args:
        juju: Jubilant object.
        expected_by_app: Mapping of app name to expected status string(s).
        timeout: Maximum seconds to wait.
        raise_on_error: If True, raise on any app entering error status.
    """
    normalized: Dict[str, set[str]] = {}
    for app, expected in expected_by_app.items():
        normalized[app] = {expected} if isinstance(expected, str) else set(expected)

    wait_kwargs: dict = {"timeout": timeout}
    if raise_on_error:
        wait_kwargs["error"] = lambda status: jubilant.any_error(status, *normalized.keys())
    juju.wait(
        lambda status: all(_app_status_current(status, app) in wanted for app, wanted in normalized.items()),
        **wait_kwargs,
    )


def wait_for_all_active(juju: jubilant.Juju, apps: Iterable[str], *, timeout: float) -> None:
    """Wait until all applications and units for apps are active.

    Args:
        juju: Jubilant object.
        apps: Application names to wait for.
        timeout: Maximum seconds to wait.
    """
    app_list = tuple(apps)
    juju.wait(
        lambda status: jubilant.all_active(status, *app_list),
        error=lambda status: jubilant.any_error(status, *app_list),
        timeout=timeout,
    )


def get_application_url(juju: jubilant.Juju, application: str, port: int) -> str:
    """Return the application URL from the model.

    Args:
        juju: Jubilant object.
        application: Name of the application.
        port: Port number of the URL.

    Returns:
        Application URL of the form {address}:{port}.
    """
    status = juju.status()
    address = status.apps[application].address
    return f"{address}:{port}"


def get_unit_url(juju: jubilant.Juju, application: str, unit: int, port: int, protocol: str = "http") -> str:
    """Return the unit URL from the model.

    Args:
        juju: Jubilant object.
        application: Name of the application.
        unit: Number of the unit.
        port: Port number of the URL.
        protocol: Transfer protocol (default: http).

    Returns:
        Unit URL of the form {protocol}://{address}:{port}.

    Raises:
        ValueError: If no reachable address is found for the unit.
    """
    status = juju.status()
    unit_name = f"{application}/{unit}"
    app_status = status.apps[application]
    unit_status = app_status.units.get(unit_name)

    address = ""
    if unit_status:
        address = unit_status.public_address or unit_status.address
    if not address:
        address = app_status.address
    if not address:
        raise ValueError(f"No reachable address found for unit '{unit_name}'")

    return f"{protocol}://{address}:{port}"


def is_healthy(juju: jubilant.Juju, unit: int = 0) -> bool:
    """Return True if the Airbyte server health endpoint reports available on a unit.

    Args:
        juju: Jubilant object.
        unit: Unit number to probe (default 0).

    Returns:
        True if the unit serves a healthy response, False otherwise.
    """
    url = f"{get_unit_url(juju, APP_NAME_AIRBYTE_SERVER, unit, INTERNAL_API_PORT)}/api/v1/health"
    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        logger.info("Health check on unit %d failed: %s", unit, exc)
        return False
    return response.status_code == 200 and bool(response.json().get("available"))


def assert_serving(juju: jubilant.Juju, unit: int = 0) -> None:
    """Assert that the Airbyte server serves a healthy response on a unit.

    Args:
        juju: Jubilant object.
        unit: Unit number to probe (default 0).
    """
    url = f"{get_unit_url(juju, APP_NAME_AIRBYTE_SERVER, unit, INTERNAL_API_PORT)}/api/v1/health"
    response = requests.get(url, timeout=300)
    assert response.status_code == 200, f"health endpoint on unit {unit} returned {response.status_code}"
    assert response.json().get("available"), f"Airbyte on unit {unit} reports unavailable"


def wait_until_healthy(juju: jubilant.Juju, unit: int = 0, attempts: int = 30, delay: float = 10.0) -> None:
    """Wait until the Airbyte server health endpoint reports available on a unit.

    Args:
        juju: Jubilant object.
        unit: Unit number to probe (default 0).
        attempts: Maximum number of attempts (default 30).
        delay: Seconds to sleep between attempts (default 10).

    Raises:
        AssertionError: If the unit never reports healthy within the attempts.
    """
    for attempt in range(1, attempts + 1):
        if is_healthy(juju, unit):
            return
        logger.info("Unit %d not healthy yet (attempt %d/%d)", unit, attempt, attempts)
        time.sleep(delay)
    raise AssertionError(f"Airbyte unit {unit} never became healthy")


def deploy_full_stack(
    juju: jubilant.Juju,
    charm: Optional[Path] = None,
    resources: Optional[dict] = None,
    *,
    channel: Optional[str] = None,
) -> None:
    """Deploy Airbyte plus its full dependency stack and wait for it to go active.

    Args:
        juju: Jubilant object for the K8s model.
        charm: Path to the charm package (required unless ``channel`` is given).
        resources: Resource-name to local image map (required unless ``channel``).
        channel: Charmhub channel to deploy Airbyte from instead of a local package.

    Raises:
        ValueError: If neither ``channel`` nor both ``charm`` and ``resources`` are given.
    """
    try:
        juju.model_config({"update-status-hook-interval": "60s"})
    except jubilant.CLIError as exc:
        logger.warning("Could not set update-status-hook-interval: %s", exc)

    logger.info("Deploying '%s'", APP_NAME_AIRBYTE_SERVER)
    if channel:
        juju.deploy(APP_NAME_AIRBYTE_SERVER, channel=channel, trust=True)
    elif charm is not None and resources is not None:
        juju.deploy(charm, resources=resources, trust=True)
    else:
        raise ValueError("deploy_full_stack requires either channel= or both charm and resources")

    juju.deploy(
        APP_NAME_TEMPORAL_SERVER, channel=TEMPORAL_CHANNEL, base=TEMPORAL_BASE, config={"num-history-shards": 4}
    )
    juju.deploy(APP_NAME_TEMPORAL_ADMIN, channel=TEMPORAL_CHANNEL, base=TEMPORAL_BASE)
    juju.deploy(POSTGRES_NAME, channel=POSTGRES_CHANNEL, revision=POSTGRES_REVISION, trust=True)
    juju.deploy(MINIO_NAME, channel=MINIO_CHANNEL)

    wait_for_apps_status(juju, {POSTGRES_NAME: "active", MINIO_NAME: "active"}, timeout=20 * 60)
    wait_for_apps_status(
        juju,
        {APP_NAME_TEMPORAL_SERVER: "blocked", APP_NAME_TEMPORAL_ADMIN: "blocked"},
        timeout=10 * 60,
        raise_on_error=False,
    )

    perform_temporal_integrations(juju)
    create_default_namespace(juju)
    perform_airbyte_integrations(juju)


def perform_temporal_integrations(juju: jubilant.Juju) -> None:
    """Integrate the Temporal server with PostgreSQL and the admin charm.

    Args:
        juju: Jubilant object.
    """
    juju.integrate(f"{APP_NAME_TEMPORAL_SERVER}:db", f"{POSTGRES_NAME}:database")
    juju.integrate(f"{APP_NAME_TEMPORAL_SERVER}:visibility", f"{POSTGRES_NAME}:database")
    juju.integrate(f"{APP_NAME_TEMPORAL_SERVER}:admin", f"{APP_NAME_TEMPORAL_ADMIN}:admin")
    # The admin charm's `cli` action resolves the server address via the
    # temporal-host-info relation; without it the action fails.
    juju.integrate(f"{APP_NAME_TEMPORAL_SERVER}:temporal-host-info", f"{APP_NAME_TEMPORAL_ADMIN}:temporal-host-info")
    wait_for_all_active(juju, [APP_NAME_TEMPORAL_SERVER, POSTGRES_NAME], timeout=10 * 60)


def create_default_namespace(juju: jubilant.Juju) -> None:
    """Create the default namespace on the Temporal server via the admin charm.

    Args:
        juju: Jubilant object.
    """
    task = juju.run(
        f"{APP_NAME_TEMPORAL_ADMIN}/0",
        "cli",
        {"args": "operator namespace --namespace default create"},
        wait=120,
    )
    logger.info("cli result: %s", task.results)
    assert task.results.get("result") == "command succeeded"


def perform_airbyte_integrations(juju: jubilant.Juju) -> None:
    """Integrate Airbyte with PostgreSQL and MinIO, then wait for it to go active.

    Args:
        juju: Jubilant object.
    """
    juju.integrate(APP_NAME_AIRBYTE_SERVER, POSTGRES_NAME)
    juju.integrate(APP_NAME_AIRBYTE_SERVER, MINIO_NAME)
    wait_for_all_active(juju, [APP_NAME_AIRBYTE_SERVER, POSTGRES_NAME, MINIO_NAME], timeout=15 * 60)


def get_db_password(juju: jubilant.Juju) -> str:
    """Return the PostgreSQL admin password via the get-password action.

    Args:
        juju: Jubilant object.

    Returns:
        The PostgreSQL admin password.

    Raises:
        ValueError: If the action does not return a password.
    """
    task = juju.run(f"{POSTGRES_NAME}/0", "get-password", wait=60)
    password = task.results.get("password", "")
    if not password:
        raise ValueError("get-password action did not return a password")
    return password


def run_sample_workflow(juju: jubilant.Juju) -> None:
    """Connect a client and run a basic Temporal workflow.

    Args:
        juju: Jubilant object.
    """
    asyncio.run(_run_sample_workflow(juju))


async def _run_sample_workflow(juju: jubilant.Juju) -> None:
    """Run the SayHello Temporal workflow and assert the greeting.

    Args:
        juju: Jubilant object.
    """
    url = get_application_url(juju, APP_NAME_TEMPORAL_SERVER, TEMPORAL_PORT)
    logger.info("running workflow on app address: %s", url)

    client = await Client.connect(url)
    async with Worker(client, task_queue="my-task-queue", workflows=[SayHello], activities=[say_hello]):
        name = "Jean-luc"
        result = await client.execute_workflow(SayHello.run, name, id="my-workflow-id", task_queue="my-task-queue")
        logger.info("result: %s", result)
        assert result == f"Hello, {name}!"


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


def post_with_retry(url, payload, *, attempts=6, timeout=120, delay=30):
    """POST to the Airbyte API, retrying to absorb workload-plane warm-up.

    Args:
        url: Target API URL.
        payload: JSON request body.
        attempts: Maximum number of attempts.
        timeout: Per-request timeout in seconds.
        delay: Seconds to sleep between attempts.

    Returns:
        The first response with HTTP 200.

    Raises:
        AssertionError: If no attempt returns HTTP 200.
    """
    last_response = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, json=payload, headers=POST_HEADERS, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            logger.info("POST %s failed: %s (attempt %d/%d)", url, exc, attempt, attempts)
        else:
            if response.status_code == 200:
                return response
            last_response = response
            logger.info("POST %s -> %d (attempt %d/%d)", url, response.status_code, attempt, attempts)
        time.sleep(delay)
    raise AssertionError(
        f"POST {url} did not return 200 after {attempts} attempts; "
        f"last status: {getattr(last_response, 'status_code', 'no response')}"
    )


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
    response = post_with_retry(url, payload)
    logger.info(response.json())

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
    response = post_with_retry(url, payload)
    logger.info(response.json())

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
        "nonBreakingSchemaUpdatesBehavior": "ignore",
        "sourceId": source_id,
        "destinationId": destination_id,
    }

    logger.info("creating Airbyte connection")
    response = post_with_retry(url, payload)
    logger.info(response.json())

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


def run_test_sync_job(juju: jubilant.Juju) -> None:
    """Run a test Airbyte connection end to end and assert it succeeds.

    Args:
        juju: Jubilant object.
    """
    api_url = get_unit_url(juju, APP_NAME_AIRBYTE_SERVER, 0, INTERNAL_API_PORT)
    logger.info("curling app address: %s", api_url)

    workspace_id = get_airbyte_workspace_id(api_url)
    db_password = get_db_password(juju)
    assert db_password

    model_name = model_short_name(juju.model or "")
    source_id = create_airbyte_source(api_url, workspace_id)
    destination_id = create_airbyte_destination(api_url, model_name, workspace_id, db_password)
    connection_id = create_airbyte_connection(api_url, source_id, destination_id)

    job_successful = False
    for i in range(4):
        logger.info("attempt %d to trigger new job", i + 1)
        job_id = trigger_airbyte_connection(api_url, connection_id)

        for j in range(15):
            logger.info("job %d attempt %d: getting job status", i + 1, j + 1)
            status = check_airbyte_job_status(api_url, job_id)

            if status == "failed":
                break

            if status == "succeeded":
                logger.info("job %d attempt %d: job successful!", i + 1, j + 1)
                job_successful = True
                break

            logger.info("job %d attempt %d: job still running, retrying in 10 seconds", i + 1, j + 1)
            time.sleep(10)

        if job_successful:
            break

        cancel_airbyte_job(api_url, job_id)

    assert job_successful
