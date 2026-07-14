# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

terraform {
  required_version = "~> 1.14"
  required_providers {
    external = {
      version = "> 2"
      source  = "hashicorp/external"
    }
  }
}

variable "model_uuid" {
  type = string
}

variable "app_name" {
  description = "Name of the temporal-admin-k8s application whose `cli` action creates the namespace."
  type        = string
}

variable "namespace" {
  description = "Temporal namespace to create."
  type        = string
  default     = "default"
}

variable "timeout" {
  description = "Seconds to keep retrying the action while the admin charm becomes ready."
  type        = number
  default     = 600
}

# Runs the temporal-admin `cli` action to create the Temporal namespace. Terraform/juju_integration
# is declarative and cannot run charm actions, so this mirrors the manual step the charm integration
# tests perform (helpers.create_default_namespace) before Airbyte can reach active.
# tflint-ignore: terraform_unused_declarations
data "external" "create_namespace" {
  program = ["bash", "${path.module}/create-namespace.sh", var.model_uuid, var.app_name, var.namespace, var.timeout]
}
