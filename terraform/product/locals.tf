# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

locals {
  # Deploy postgresql-k8s in-module unless an external database offer URL is supplied.
  deploy_database = var.database_offer_url == ""

  # The PostgreSQL side of the database integrations: the in-module application endpoint when
  # deployed here, or the external offer URL otherwise. Consumed by the Airbyte and Temporal
  # database relations so both share one database backend.
  database_endpoint = {
    name      = local.deploy_database ? one(juju_application.postgresql_k8s[*].name) : null
    endpoint  = local.deploy_database ? "database" : null
    offer_url = local.deploy_database ? null : var.database_offer_url
  }
}
