# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "model_uuid" {
  description = "UUID of the model the product is deployed into."
  value       = var.model_uuid
}

output "applications" {
  description = "Names of the deployed applications. postgresql-k8s is present only when deployed in-module."
  value = merge(
    {
      airbyte-k8s        = module.airbyte.app_name
      temporal-k8s       = juju_application.temporal_k8s.name
      temporal-admin-k8s = juju_application.temporal_admin_k8s.name
      minio              = juju_application.minio.name
    },
    local.deploy_database ? { postgresql-k8s = one(juju_application.postgresql_k8s[*].name) } : {},
  )
}

output "database_offer_url" {
  description = "The external database offer URL in use, or null when PostgreSQL is deployed in-module."
  value       = local.deploy_database ? null : var.database_offer_url
}
