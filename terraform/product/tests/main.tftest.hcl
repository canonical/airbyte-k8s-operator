# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Defaults match CI (operator-workflows registers the K8s cloud as `tfk8s`). For local runs pass
# globals via environment, e.g.:
#   TF_VAR_k8s_cloud_name=microk8s TF_VAR_k8s_credential_name=microk8s \
#   TF_VAR_k8s_workload_storage=microk8s-hostpath terraform test
run "setup_tests" {
  module {
    source = "./tests/setup"
  }
}

run "full_deploy" {
  variables {
    model_uuid = run.setup_tests.model_uuid
  }

  assert {
    condition     = output.applications["airbyte-k8s"] == "airbyte-k8s"
    error_message = "airbyte-k8s application not present in the deployed applications"
  }

  assert {
    condition     = output.applications["temporal-k8s"] == "temporal-k8s" && output.applications["minio"] == "minio"
    error_message = "expected dependency applications were not deployed"
  }
}

# Assert the full stack converges: airbyte-k8s only reaches active once its database and object
# storage are related and its auth/dataplane credentials are resolved.
run "wait_for_airbyte_active" {
  module {
    source = "./tests/wait_for_active"
  }

  variables {
    model_uuid = run.setup_tests.model_uuid
    app_name   = "airbyte-k8s"
    timeout    = 1800
  }

  assert {
    condition     = data.external.app_status.result.status == "active"
    error_message = "airbyte-k8s did not reach active state"
  }
}
