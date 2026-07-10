# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

run "setup_tests" {
  module {
    source = "./tests/setup"
  }
}

run "basic_deploy" {
  variables {
    model_uuid = run.setup_tests.model_uuid
    channel    = "latest/edge"
  }

  assert {
    condition     = output.app_name == "airbyte-k8s"
    error_message = "airbyte-k8s app_name did not match expected"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "requires.db endpoint did not match expected"
  }

  assert {
    condition     = output.requires.object_storage == "object-storage"
    error_message = "requires.object_storage endpoint did not match expected"
  }
}
