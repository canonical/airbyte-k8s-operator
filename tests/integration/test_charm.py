#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Airbyte charm deployment integration tests."""

import json
import logging
from pathlib import Path

import helpers
import jubilant
import pytest

logger = logging.getLogger(__name__)

TRAEFIK_NAME = "traefik-k8s"
TRAEFIK_CHANNEL = "latest/stable"
AWS_CREDENTIALS_SECRET_NAME = "airbyte-aws-credentials"  # nosec


@pytest.fixture(scope="module")
def deployed_stack(k8s_juju: jubilant.Juju, charm: Path, rock_resources: dict) -> jubilant.Juju:
    """Deploy the local Airbyte charm with its full dependency stack, active.

    Args:
        k8s_juju: Jubilant object for the K8s model.
        charm: Path to the local charm package.
        rock_resources: Local rock resource image map.

    Returns:
        The Jubilant object with Airbyte active.
    """
    helpers.deploy_full_stack(k8s_juju, charm, rock_resources)
    helpers.run_sample_workflow(k8s_juju)
    return k8s_juju


def test_deployment(deployed_stack: jubilant.Juju):
    """Airbyte serves a healthy response on its API port."""
    helpers.assert_serving(deployed_stack)


def test_sync_job(deployed_stack: jubilant.Juju):
    """Airbyte runs a sample source-to-destination sync job to completion."""
    helpers.run_test_sync_job(deployed_stack)


def test_ingress(deployed_stack: jubilant.Juju):
    """Airbyte exposes itself over the standard ingress interface via Traefik.

    FE uses Traefik for customer deployments, so this verifies the charm's
    ingress relation works with it: integrate over `ingress`, then confirm
    Traefik publishes a proxied URL for the Airbyte app.
    """
    juju = deployed_stack
    juju.deploy(TRAEFIK_NAME, channel=TRAEFIK_CHANNEL, trust=True)
    juju.integrate(f"{helpers.APP_NAME_AIRBYTE_SERVER}:ingress", f"{TRAEFIK_NAME}:ingress")
    helpers.wait_for_apps_status(juju, {TRAEFIK_NAME: "active"}, timeout=10 * 60, raise_on_error=False)

    task = juju.run(f"{TRAEFIK_NAME}/0", "show-proxied-endpoints", wait=60)
    proxied_endpoints = json.loads(task.results["proxied-endpoints"])
    assert helpers.APP_NAME_AIRBYTE_SERVER in proxied_endpoints

    # Ingress restarts the server (new AIRBYTE_URL), so wait for it to serve again.
    helpers.wait_until_healthy(juju)


def test_optional_credentials_secret(deployed_stack: jubilant.Juju):
    """Credential secrets are optional, and a configured one resolves without blocking.

    The AWS/GCP/Vault credential secrets are not required for Airbyte to be
    active, so the charm is already active with none configured. Opting in to one
    (created, granted, and referenced by config) must keep the charm active,
    exercising the real Juju secret grant + resolution path.
    """
    juju = deployed_stack

    # Secrets are optional: the charm is active without any configured.
    helpers.assert_serving(juju)

    # Opt in to a credential secret and grant the charm access to it.
    secret_uri = juju.add_secret(
        AWS_CREDENTIALS_SECRET_NAME,
        {"aws-access-key": "AKIAEXAMPLE", "aws-secret-access-key": "s3cr3t"},  # nosec
    )
    juju.grant_secret(AWS_CREDENTIALS_SECRET_NAME, helpers.APP_NAME_AIRBYTE_SERVER)
    juju.config(helpers.APP_NAME_AIRBYTE_SERVER, {"aws-credentials-secret-id": str(secret_uri)})

    # Resolving the granted secret must keep the charm active, not block it.
    helpers.wait_for_all_active(juju, [helpers.APP_NAME_AIRBYTE_SERVER], timeout=10 * 60)
