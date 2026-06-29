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
AWS_CREDENTIALS_SECRET_NAME = "airbyte-aws-credentials"  # nosec


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
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME_AIRBYTE_SERVER, TRAEFIK_NAME], status="active", raise_on_blocked=False, timeout=600
        )

        action = await ops_test.model.applications[TRAEFIK_NAME].units[0].run_action("show-proxied-endpoints")
        result = await action.wait()
        proxied_endpoints = json.loads(result.results["proxied-endpoints"])
        assert APP_NAME_AIRBYTE_SERVER in proxied_endpoints

    async def test_optional_credentials_secret(self, ops_test: OpsTest):
        """Credential secrets are optional, and a configured one resolves without blocking.

        The AWS/GCP/Vault credential secrets are not required for Airbyte to be
        active, so the charm is already active with none configured. Opting in to
        one (created, granted, and referenced by config) must keep the charm
        active, exercising the real Juju secret grant + resolution path.
        """
        app = ops_test.model.applications[APP_NAME_AIRBYTE_SERVER]

        # Secrets are optional: the charm is active without any configured.
        assert app.units[0].workload_status == "active"

        # Opt in to a credential secret and grant the charm access to it.
        secret_uri = await ops_test.model.add_secret(
            AWS_CREDENTIALS_SECRET_NAME,
            ["aws-access-key=AKIAEXAMPLE", "aws-secret-access-key=s3cr3t"],  # nosec
        )
        await ops_test.model.grant_secret(AWS_CREDENTIALS_SECRET_NAME, APP_NAME_AIRBYTE_SERVER)
        await app.set_config({"aws-credentials-secret-id": secret_uri})

        # Resolving the granted secret must keep the charm active, not block it.
        await ops_test.model.wait_for_idle(apps=[APP_NAME_AIRBYTE_SERVER], status="active", timeout=600)
