#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
import requests
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME_AIRBYTE_SERVER, get_unit_url
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for charm."""

    async def test_deployment(self, ops_test: OpsTest):
        url = await get_unit_url(ops_test, application=APP_NAME_AIRBYTE_SERVER, unit=0, port=8001)
        logger.info("curling app address: %s", url)

        response = requests.get(f"{url}/api/v1/health", timeout=300)
        print(response.json())
        assert response.status_code == 200
        assert response.json().get("available")
