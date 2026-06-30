#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Upgrade regression test: refresh the published Airbyte charm to the local build."""

import logging
from pathlib import Path

import helpers
import jubilant
import pytest

logger = logging.getLogger(__name__)

BASELINE_CHANNEL = "latest/edge"


@pytest.fixture(scope="module")
def baseline_stack(k8s_juju: jubilant.Juju) -> jubilant.Juju:
    """Deploy the published (baseline) Airbyte charm with its full stack, active.

    Args:
        k8s_juju: Jubilant object for the K8s model.

    Returns:
        The Jubilant object with the baseline Airbyte active.
    """
    logger.info("Deploying '%s' from channel '%s'", helpers.APP_NAME_AIRBYTE_SERVER, BASELINE_CHANNEL)
    helpers.deploy_full_stack(k8s_juju, channel=BASELINE_CHANNEL)
    return k8s_juju


def test_refresh_from_published(baseline_stack: jubilant.Juju, charm: Path, rock_resources: dict):
    """The published charm refreshes in place to the local build and keeps serving.

    Validates upgrade safety (AC1): the workload is available before the upgrade,
    recovers to active afterwards, and serves a healthy response post-upgrade.
    """
    juju = baseline_stack

    logger.info("Verifying the baseline serves before the refresh")
    helpers.assert_serving(juju)

    logger.info("Refreshing '%s' to the local charm + local rock", helpers.APP_NAME_AIRBYTE_SERVER)
    juju.refresh(helpers.APP_NAME_AIRBYTE_SERVER, path=charm, resources=rock_resources)

    # Let the upgrade-charm / config-changed reconcile churn settle, then require active.
    juju.wait(lambda status: jubilant.all_agents_idle(status, helpers.APP_NAME_AIRBYTE_SERVER), timeout=10 * 60)
    helpers.wait_for_all_active(juju, [helpers.APP_NAME_AIRBYTE_SERVER], timeout=20 * 60)

    logger.info("Verifying the refreshed charm still serves")
    helpers.wait_until_healthy(juju)
    helpers.assert_serving(juju)
