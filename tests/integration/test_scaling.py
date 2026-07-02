#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaling test: Airbyte scales out to 3 units and back in to 1."""

import logging
from pathlib import Path

import helpers
import jubilant
import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def scaled_stack(k8s_juju: jubilant.Juju, charm: Path, rock_resources: dict) -> jubilant.Juju:
    """Deploy the local Airbyte charm with its full stack at one unit, active.

    Args:
        k8s_juju: Jubilant object for the K8s model.
        charm: Path to the local charm package.
        rock_resources: Local rock resource image map.

    Returns:
        The Jubilant object with Airbyte active at one unit.
    """
    helpers.deploy_full_stack(k8s_juju, charm, rock_resources)
    return k8s_juju


def test_scale_out_and_in(scaled_stack: jubilant.Juju):
    """Scale 1 -> 3 -> 1, staying active and serving throughout (AC2)."""
    juju = scaled_stack
    app = helpers.APP_NAME_AIRBYTE_SERVER

    logger.info("Verifying the single unit serves before scaling")
    helpers.assert_serving(juju, unit=0)

    logger.info("Scaling out to 3 units")
    juju.add_unit(app, num_units=2)
    juju.wait(
        lambda status: jubilant.all_active(status, app) and len(status.apps[app].units) == 3,
        error=lambda status: jubilant.any_error(status, app),
        timeout=30 * 60,
    )

    logger.info("Verifying every unit serves a healthy response")
    for unit in range(3):
        helpers.wait_until_healthy(juju, unit=unit)

    logger.info("Verifying a sync job runs end to end while scaled out")
    helpers.run_test_sync_job(juju)

    logger.info("Scaling back in to 1 unit")
    juju.remove_unit(app, num_units=2)
    juju.wait(
        lambda status: jubilant.all_active(status, app) and len(status.apps[app].units) == 1,
        error=lambda status: jubilant.any_error(status, app),
        timeout=20 * 60,
    )

    logger.info("Verifying the surviving unit still serves")
    helpers.wait_until_healthy(juju, unit=0)
    helpers.assert_serving(juju, unit=0)
