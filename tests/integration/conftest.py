# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration test config."""

import asyncio
import logging

import pytest_asyncio
from helpers import (
    APP_NAME_AIRBYTE_SERVER,
    APP_NAME_TEMPORAL_ADMIN,
    APP_NAME_TEMPORAL_SERVER,
    create_default_namespace,
    get_airbyte_charm_resources,
    perform_airbyte_integrations,
    perform_temporal_integrations,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest):
    """Test the app is up and running."""
    charm = await ops_test.build_charm(".")
    resources = get_airbyte_charm_resources()

    asyncio.gather(
        ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME_AIRBYTE_SERVER, trust=True),
        ops_test.model.deploy(
            APP_NAME_TEMPORAL_SERVER,
            channel="edge",
            config={"num-history-shards": 1},
        ),
        ops_test.model.deploy(APP_NAME_TEMPORAL_ADMIN, channel="edge"),
        ops_test.model.deploy("postgresql-k8s", channel="14/stable", trust=True),
        ops_test.model.deploy("minio", channel="edge"),
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=["postgresql-k8s", "minio"], status="active", raise_on_blocked=False, timeout=1200
        )
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME_TEMPORAL_SERVER, APP_NAME_TEMPORAL_ADMIN],
            status="blocked",
            raise_on_blocked=False,
            timeout=600,
        )

        await perform_temporal_integrations(ops_test)
        await create_default_namespace(ops_test)

        await perform_airbyte_integrations(ops_test)
