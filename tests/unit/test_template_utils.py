#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for template rendering utilities."""

import unittest

from template_utils import render_template


class TestTemplateUtils(unittest.TestCase):
    """Test template rendering functionality."""

    def test_render_flags_template_all_values(self):
        """Test rendering flags template with all values set."""
        context = {
            "heartbeat_max_seconds_between_messages": 3600,
            "heartbeat_fail_sync": True,
            "destination_timeout_max_seconds": 86400,
            "destination_timeout_fail_sync": False,
        }

        output = render_template("flags.yaml.j2", context)

        self.assertIn("flags:", output)
        self.assertIn("heartbeat-max-seconds-between-messages", output)
        self.assertIn('serve: "3600"', output)
        self.assertIn("heartbeat.failSync", output)
        self.assertIn("serve: true", output)
        self.assertIn("destination-timeout-enabled", output)
        self.assertIn("destination-timeout.seconds", output)
        self.assertIn('serve: "86400"', output)
        self.assertIn("destination-timeout.failSync", output)
        self.assertIn("serve: false", output)

    def test_render_flags_template_heartbeat_only(self):
        """Test rendering flags template with only heartbeat values."""
        context = {
            "heartbeat_max_seconds_between_messages": 1800,
            "heartbeat_fail_sync": None,
            "destination_timeout_max_seconds": None,
            "destination_timeout_fail_sync": None,
        }

        output = render_template("flags.yaml.j2", context)

        self.assertIn("flags:", output)
        self.assertIn("heartbeat-max-seconds-between-messages", output)
        self.assertIn('serve: "1800"', output)
        self.assertNotIn("heartbeat.failSync", output)
        self.assertNotIn("destination-timeout", output)

    def test_render_flags_template_destination_timeout_only(self):
        """Test rendering flags template with only destination timeout values."""
        context = {
            "heartbeat_max_seconds_between_messages": None,
            "heartbeat_fail_sync": None,
            "destination_timeout_max_seconds": 43200,
            "destination_timeout_fail_sync": True,
        }

        output = render_template("flags.yaml.j2", context)

        self.assertIn("flags:", output)
        self.assertIn("destination-timeout-enabled", output)
        self.assertIn("destination-timeout.seconds", output)
        self.assertIn('serve: "43200"', output)
        self.assertIn("destination-timeout.failSync", output)
        self.assertIn("serve: true", output)
        self.assertNotIn("heartbeat-max-seconds-between-messages", output)
        self.assertNotIn("heartbeat.failSync", output)


if __name__ == "__main__":
    unittest.main()
