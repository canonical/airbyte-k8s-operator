# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration test config."""

import logging
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Dict

import jubilant
import pytest
from pytest import FixtureRequest

logger = logging.getLogger(__name__)

LXD_CONTROLLER = "localhost-localhost"
K8S_CLOUD = "canonical-k8s"


@pytest.fixture(scope="session", autouse=True)
def setup_canonical_k8s(request: FixtureRequest):
    """Register Canonical Kubernetes as a Juju cloud before any tests run.

    Args:
        request: pytest request, used to read the --kube-config option.

    Raises:
        RuntimeError: If the canonical-k8s cloud cannot be registered.
    """
    logger.info("Bootstrapping the Juju controller and Canonical Kubernetes cloud.")

    # Host the controller on LXD; canonical-k8s is added to it as a K8s cloud below.
    subprocess.run(["/snap/bin/juju", "bootstrap", "localhost", LXD_CONTROLLER], check=False)  # nosec B603

    # The kubeconfig path is supplied by operator-workflows via --kube-config;
    # default to the conventional location.
    kubeconfig = os.path.expanduser(request.config.getoption("--kube-config") or "~/.kube/config")

    # Register the canonical-k8s cluster as a cloud on the LXD controller.
    # `juju add-k8s` reads the cluster + credential from $KUBECONFIG.
    result = subprocess.run(
        ["/snap/bin/juju", "add-k8s", K8S_CLOUD, "--client", "--controller", LXD_CONTROLLER],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "KUBECONFIG": kubeconfig},
    )  # nosec B603
    if result.returncode != 0:
        if "already exists" in result.stderr or "already exists" in result.stdout:
            logger.info("Canonical Kubernetes cloud already configured")
        else:
            raise RuntimeError(f"Failed to add canonical-k8s cloud.\nStdout: {result.stdout}\nStderr: {result.stderr}")


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
    """Create a temporary Canonical Kubernetes model for the full deployment tests.

    Args:
        request: pytest request, used to collect logs on failure.

    Yields:
        Jubilant object bound to a fresh K8s model.
    """
    with jubilant.temp_model(cloud=K8S_CLOUD) as juju:
        juju.wait_timeout = 30 * 60
        yield juju
        _collect_juju_logs_if_failed(request, juju)
