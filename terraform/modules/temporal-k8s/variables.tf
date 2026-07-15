# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Name of the application in the Juju model."
  type        = string
  default     = "temporal-k8s"
}

variable "base" {
  description = "The operating system on which to deploy."
  type        = string
  default     = "ubuntu@24.04"
}

variable "channel" {
  description = "The channel to use when deploying the charm."
  type        = string
  default     = "1.23/stable"
}

variable "config" {
  description = "Application configuration. Options at https://charmhub.io/temporal-k8s/configurations."
  type        = map(string)
  default     = {}
}

variable "constraints" {
  description = "Juju constraints to apply to the application."
  type        = string
  default     = null
}

variable "model_uuid" {
  description = "UUID of the Juju model to deploy into."
  type        = string
  nullable    = false
}

variable "resources" {
  description = "Map of OCI-image resources to use instead of the charm's bundled images."
  type        = map(string)
  default     = {}
}

variable "revision" {
  description = "Charm revision to deploy."
  type        = number
  default     = null
}

variable "units" {
  description = "Number of units to deploy."
  type        = number
  default     = 1
}
