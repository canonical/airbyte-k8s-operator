# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for charm tests."""

import pytest


def pytest_addoption(parser: pytest.Parser):
    """Parse additional pytest options.

    Args:
        parser: pytest command line parser.
    """
    # The prebuilt charm file.
    parser.addoption("--charm-file", action="append", default=[])
    # The charm image name:tag.
    parser.addoption("--airbyte-image", action="store", default="")

    # Passed by integration_test_run.yaml.
    parser.addoption("--model", action="store", default=None)
    parser.addoption("--keep-models", action="store_true", default=False)
    parser.addoption("--series", action="store", default=None)

    # Passed by operator-workflows when use-canonical-k8s: true.
    parser.addoption("--kube-config", action="store", default=None)
