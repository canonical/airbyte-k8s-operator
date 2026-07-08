# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration test config."""

import logging
import os
import sys
from pathlib import Path
from typing import Dict

import jubilant
import pytest
from pytest import FixtureRequest

logger = logging.getLogger(__name__)


def _collect_juju_logs_if_failed(request: FixtureRequest, juju: jubilant.Juju) -> None:
    """Print Juju logs at teardown time when tests fail.

    Args:
        request: pytest request, used to detect test failures.
        juju: Jubilant object for the model to collect logs from.
    """
    if not request.session.testsfailed:
        return
    logger.info("Collecting Juju logs from model '%s'", juju.model)
    log = juju.debug_log(limit=1000)
    print(log, end="", file=sys.stderr)


@pytest.fixture(scope="session")
def charm(request: FixtureRequest) -> Path:
    """Return the path to the charm package to deploy.

    Args:
        request: pytest request, used to read the --charm-file option.

    Returns:
        Path to the charm package.

    Raises:
        FileNotFoundError: If no charm package can be located.
        ValueError: If more than one charm package is present.
    """
    charm_file = request.config.getoption("--charm-file")
    if charm_file:
        charm_path = Path(charm_file[0]).expanduser().resolve()
        if not charm_path.exists():
            raise FileNotFoundError(f"Charm does not exist: {charm_path}")
        return charm_path

    charm_path_env = os.environ.get("CHARM_PATH")
    if charm_path_env:
        charm_path = Path(charm_path_env).expanduser().resolve()
        if not charm_path.exists():
            raise FileNotFoundError(f"Charm does not exist: {charm_path}")
        return charm_path

    charm_paths = list(Path(".").glob("*.charm"))
    if not charm_paths:
        raise FileNotFoundError("No .charm file in current directory")
    if len(charm_paths) > 1:
        path_list = ", ".join(str(path) for path in charm_paths)
        raise ValueError(f"More than one .charm file in current directory: {path_list}")
    return charm_paths[0].resolve()


@pytest.fixture(scope="session")
def rock_resources(request: FixtureRequest) -> Dict[str, str]:
    """Provide the rock resource image deployed locally by operator-workflows.

    Args:
        request: pytest request, used to read the --airbyte-image option.

    Returns:
        Mapping of the charm's resource name to its local registry image.

    Raises:
        ValueError: If the required resource image option is missing.
    """
    image = request.config.getoption("--airbyte-image")
    if image in {"", "None", "none", None}:
        raise ValueError("Missing required resource image option: --airbyte-image")
    return {"airbyte-image": str(image)}


@pytest.fixture(scope="module")
def k8s_juju(request: FixtureRequest) -> jubilant.Juju:
    """Provide the Juju model for the full deployment tests.

    Args:
        request: pytest request, used to read --model and collect logs on failure.

    Yields:
        Jubilant object bound to the model.
    """
    model_name = request.config.getoption("--model")
    if model_name:
        juju = jubilant.Juju(model=model_name)
        juju.wait_timeout = 30 * 60
        try:
            yield juju
        finally:
            _collect_juju_logs_if_failed(request, juju)
    else:
        with jubilant.temp_model() as juju:
            juju.wait_timeout = 30 * 60
            yield juju
            _collect_juju_logs_if_failed(request, juju)
