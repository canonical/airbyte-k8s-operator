# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "temporal_k8s" {
  name       = var.app_name
  model_uuid = var.model_uuid

  charm {
    name     = "temporal-k8s"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config      = var.config
  constraints = var.constraints
  resources   = var.resources
  units       = var.units
}
