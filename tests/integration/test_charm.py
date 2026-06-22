#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
import requests
from helpers import APP_NAME_AIRBYTE_SERVER, get_unit_url, run_test_sync_job
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

INGRESS_INTEGRATOR_NAME = "nginx-ingress-integrator"
INGRESS_HOSTNAME = "airbyte.test"


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for charm."""

    async def test_deployment(self, ops_test: OpsTest):
        url = await get_unit_url(ops_test, application=APP_NAME_AIRBYTE_SERVER, unit=0, port=8001)
        logger.info("curling app address: %s", url)

        response = requests.get(f"{url}/api/v1/health", timeout=300)

        assert response.status_code == 200
        assert response.json().get("available")

    async def test_sync_job(self, ops_test: OpsTest):
        await run_test_sync_job(ops_test)

    async def test_ingress(self, ops_test: OpsTest):
        """Airbyte exposes itself over the standard ingress interface.

        Deploys an ingress provider, integrates over the `ingress` relation, and
        verifies the provider creates a route from the relation data the charm publishes.
        """
        await ops_test.model.deploy(INGRESS_INTEGRATOR_NAME, channel="latest/stable", trust=True)
        await ops_test.model.applications[INGRESS_INTEGRATOR_NAME].set_config({"service-hostname": INGRESS_HOSTNAME})
        await ops_test.model.integrate(f"{APP_NAME_AIRBYTE_SERVER}:ingress", f"{INGRESS_INTEGRATOR_NAME}:ingress")
        await ops_test.model.wait_for_idle(
            apps=[INGRESS_INTEGRATOR_NAME], status="active", raise_on_blocked=False, timeout=600
        )

        unit = ops_test.model.applications[INGRESS_INTEGRATOR_NAME].units[0]
        assert "Ingress IP" in unit.workload_status_message
