# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "applications" {
  description = "Names of the deployed applications. postgresql-k8s is present only when deployed in-module."
  value = merge(
    {
      airbyte-k8s        = module.airbyte.app_name
      temporal-k8s       = module.temporal_k8s.app_name
      temporal-admin-k8s = module.temporal_admin_k8s.app_name
      minio              = module.minio.app_name
    },
    local.deploy_database ? { postgresql-k8s = one(module.postgresql_k8s[*].app_name) } : {},
  )
}

output "database_offer_url" {
  description = "The external database offer URL in use, or null when PostgreSQL is deployed in-module."
  value       = local.deploy_database ? null : var.database_offer_url
}

output "metadata" {
  description = "Metadata for the product deployment."
  value = {
    version     = "0.1.0"
    deployed_at = plantimestamp()
    updated_at  = plantimestamp()
  }
}

output "models" {
  description = "Map of the model key to the UUID and components deployed in it."
  value = {
    main = {
      model_uuid = var.model_uuid
      components = merge(
        {
          airbyte-k8s        = module.airbyte.app_name
          temporal-k8s       = module.temporal_k8s.app_name
          temporal-admin-k8s = module.temporal_admin_k8s.app_name
          minio              = module.minio.app_name
        },
        local.deploy_database ? { postgresql-k8s = one(module.postgresql_k8s[*].app_name) } : {},
      )
    }
  }
}
