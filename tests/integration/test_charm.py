#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging

import pytest
import requests
from helpers import APP_NAME_AIRBYTE_SERVER, get_unit_url, run_test_sync_job
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

TRAEFIK_NAME = "traefik-k8s"


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
        """Airbyte exposes itself over the standard ingress interface via Traefik.

        FE uses Traefik for customer deployments, so this verifies
        the charm's ingress relation works with it: integrate over `ingress`, then
        confirm Traefik publishes a proxied URL for the Airbyte app.
        """
        await ops_test.model.deploy(TRAEFIK_NAME, channel="latest/stable", trust=True)
        await ops_test.model.integrate(f"{APP_NAME_AIRBYTE_SERVER}:ingress", f"{TRAEFIK_NAME}:ingress")
        await ops_test.model.wait_for_idle(apps=[TRAEFIK_NAME], status="active", raise_on_blocked=False, timeout=600)

        action = await ops_test.model.applications[TRAEFIK_NAME].units[0].run_action("show-proxied-endpoints")
        result = await action.wait()
        proxied_endpoints = json.loads(result.results["proxied-endpoints"])
        assert APP_NAME_AIRBYTE_SERVER in proxied_endpoints
