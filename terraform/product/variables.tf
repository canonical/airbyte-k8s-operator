# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

variable "model_uuid" {
  description = "UUID of the Kubernetes Juju model to deploy Airbyte and its dependencies into."
  type        = string
}

variable "airbyte" {
  description = "Configuration for the airbyte-k8s charm."
  type = object({
    app_name    = optional(string, "airbyte-k8s")
    channel     = optional(string, "latest/edge")
    revision    = optional(number)
    base        = optional(string, "ubuntu@22.04")
    constraints = optional(string)
    config      = optional(map(string), {})
    resources   = optional(map(string), {})
    trust       = optional(bool, true)
    units       = optional(number, 1)
  })
  default = {}
}

variable "database_offer_url" {
  description = <<-EOT
    Offer URL for an external PostgreSQL `database` endpoint (e.g. a managed database on another
    controller). Leave empty to deploy postgresql-k8s in-module and relate Airbyte and Temporal
    to it; set it to relate them to the external database instead (postgresql-k8s is not deployed).
  EOT
  type        = string
  default     = ""
}

variable "postgresql" {
  description = "Configuration for the postgresql-k8s charm (shared database for Airbyte and Temporal; used when database_offer_url is empty)."
  type = object({
    app_name           = optional(string, "postgresql-k8s")
    channel            = optional(string, "14/stable")
    revision           = optional(number, 381)
    base               = optional(string, "ubuntu@22.04")
    constraints        = optional(string)
    config             = optional(map(string), {})
    storage_directives = optional(map(string), {})
    units              = optional(number, 1)
  })
  default = {}
}

variable "temporal" {
  description = "Configuration for the temporal-k8s charm (Airbyte's workflow engine)."
  type = object({
    app_name = optional(string, "temporal-k8s")
    channel  = optional(string, "1.23/stable")
    revision = optional(number)
    base     = optional(string, "ubuntu@24.04")
    config   = optional(map(string), { num-history-shards = "4" })
    units    = optional(number, 1)
  })
  default = {}
}

variable "temporal_admin" {
  description = "Configuration for the temporal-admin-k8s charm (Temporal schema management)."
  type = object({
    app_name = optional(string, "temporal-admin-k8s")
    channel  = optional(string, "1.23/stable")
    revision = optional(number)
    base     = optional(string, "ubuntu@24.04")
    units    = optional(number, 1)
  })
  default = {}
}

variable "minio" {
  description = "Configuration for the minio charm (Airbyte object storage)."
  type = object({
    app_name           = optional(string, "minio")
    channel            = optional(string, "1.10/stable")
    revision           = optional(number)
    base               = optional(string, "ubuntu@22.04")
    config             = optional(map(string), {})
    storage_directives = optional(map(string), {})
    units              = optional(number, 1)
  })
  default = {}
}
