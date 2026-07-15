# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

locals {
  # Deploy postgresql-k8s in-module unless an external database offer URL is supplied.
  deploy_database = var.database_offer_url == ""

  configured_channels = {
    airbyte        = var.airbyte.channel
    postgresql     = var.postgresql.channel
    temporal       = var.temporal.channel
    temporal_admin = var.temporal_admin.channel
    minio          = var.minio.channel
  }

  channels = {
    for name, channel in local.configured_channels :
    name => var.risk == null ? channel : "${length(split("/", channel)) > 1 ? split("/", channel)[0] : "latest"}/${var.risk}"
  }

  # The PostgreSQL side of the database integrations: the in-module application endpoint when
  # deployed here, or the external offer URL otherwise. Consumed by the Airbyte and Temporal
  # database relations so both share one database backend.
  database_endpoint = {
    name      = local.deploy_database ? one(module.postgresql_k8s[*].app_name) : null
    endpoint  = local.deploy_database ? one(module.postgresql_k8s[*].provides["database"]) : null
    offer_url = local.deploy_database ? null : var.database_offer_url
  }
}
