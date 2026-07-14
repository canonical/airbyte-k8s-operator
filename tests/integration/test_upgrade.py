#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Upgrade regression test: refresh the published Airbyte charm to the local build."""

import json
import logging
import urllib.request
from pathlib import Path

import helpers
import jubilant
import pytest

logger = logging.getLogger(__name__)

BASELINE_CHANNEL = "latest/edge"


PREVIOUS_MAJOR_STABLE_CHANNEL = "1/stable"


def _published_channels(charm_name: str) -> set[str]:
    """Return the set of ``track/risk`` channels published for a charm on Charmhub.

    Args:
        charm_name: Name of the charm to query.

    Returns:
        The set of published ``track/risk`` channels, or an empty set if the channel list could
        not be determined (e.g. Charmhub is unreachable), so callers can skip rather than fail.
    """
    url = f"https://api.charmhub.io/v2/charms/info/{charm_name}?fields=channel-map"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # nosec B310 - fixed https charmhub API
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001 - network error / charm-not-found: treat as "unknown"
        logger.warning("Could not query published channels for %s: %s", charm_name, exc)
        return set()
    return {f"{cm['channel']['track']}/{cm['channel']['risk']}" for cm in data.get("channel-map", [])}


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

    logger.info("Verifying a sync job runs end to end after the upgrade")
    helpers.run_test_sync_job(juju)


def test_major_upgrade(charm: Path, rock_resources: dict):
    """The previous major's stable charm refreshes to the local build and keeps serving.

    Args:
        charm: Path to the locally built charm package.
        rock_resources: Resource-name to local image map for the local build.
    """
    published = _published_channels(helpers.APP_NAME_AIRBYTE_SERVER)
    if PREVIOUS_MAJOR_STABLE_CHANNEL not in published:
        pytest.skip(
            f"channel '{PREVIOUS_MAJOR_STABLE_CHANNEL}' is not published (or Charmhub is "
            "unreachable) - major upgrade not testable yet"
        )

    with jubilant.temp_model() as juju:
        juju.wait_timeout = 30 * 60

        logger.info("Deploying baseline full stack from '%s'", PREVIOUS_MAJOR_STABLE_CHANNEL)
        helpers.deploy_full_stack(juju, channel=PREVIOUS_MAJOR_STABLE_CHANNEL)

        logger.info("Verifying the previous major serves before the refresh")
        helpers.assert_serving(juju)

        logger.info("Refreshing '%s' to the local charm + local rock", helpers.APP_NAME_AIRBYTE_SERVER)
        juju.refresh(helpers.APP_NAME_AIRBYTE_SERVER, path=charm, resources=rock_resources)

        # Let the upgrade-charm / config-changed reconcile churn settle, then require active.
        juju.wait(lambda status: jubilant.all_agents_idle(status, helpers.APP_NAME_AIRBYTE_SERVER), timeout=10 * 60)
        helpers.wait_for_all_active(juju, [helpers.APP_NAME_AIRBYTE_SERVER], timeout=20 * 60)

        logger.info("Verifying the refreshed charm still serves and syncs after the major upgrade")
        helpers.wait_until_healthy(juju)
        helpers.assert_serving(juju)
        helpers.run_test_sync_job(juju)
