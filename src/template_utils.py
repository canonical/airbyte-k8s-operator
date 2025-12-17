#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Template rendering utilities for the Airbyte charm."""

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def render_template(template_name: str, context: dict) -> str:
    """Render a Jinja2 template with the given context.

    Args:
        template_name: Name of the template file (e.g., "flags.jinja").
        context: Dictionary of variables to pass to the template.

    Returns:
        Rendered template content as a string.
    """
    # Get the absolute path of templates directory
    charm_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir)
    )
    templates_path = os.path.join(charm_dir, "templates")

    # Create Jinja2 environment and render template
    loader = FileSystemLoader(templates_path)
    env = Environment(loader=loader, autoescape=True)
    template = env.get_template(template_name)

    return template.render(**context)
