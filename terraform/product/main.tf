# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

### AIRBYTE (via the base charm module)

module "airbyte" {
  source = "../charm"

  app_name    = var.airbyte.app_name
  model_uuid  = var.model_uuid
  channel     = local.channels.airbyte
  revision    = var.airbyte.revision
  base        = var.airbyte.base
  config      = var.airbyte.config
  constraints = var.airbyte.constraints
  resources   = var.airbyte.resources
  trust       = var.airbyte.trust
  units       = var.airbyte.units
}

### DEPENDENCIES

module "postgresql_k8s" {
  count  = local.deploy_database ? 1 : 0
  source = "../modules/postgresql-k8s"

  app_name           = var.postgresql.app_name
  model_uuid         = var.model_uuid
  channel            = local.channels.postgresql
  revision           = var.postgresql.revision
  base               = var.postgresql.base
  config             = var.postgresql.config
  constraints        = var.postgresql.constraints
  resources          = var.postgresql.resources
  storage_directives = var.postgresql.storage_directives
  units              = var.postgresql.units
}

module "temporal_k8s" {
  source = "../modules/temporal-k8s"

  app_name   = var.temporal.app_name
  model_uuid = var.model_uuid
  channel    = local.channels.temporal
  revision   = var.temporal.revision
  base       = var.temporal.base
  config     = var.temporal.config
  resources  = var.temporal.resources
  units      = var.temporal.units
}

module "temporal_admin_k8s" {
  source = "../modules/temporal-admin-k8s"

  app_name   = var.temporal_admin.app_name
  model_uuid = var.model_uuid
  channel    = local.channels.temporal_admin
  revision   = var.temporal_admin.revision
  base       = var.temporal_admin.base
  config     = var.temporal_admin.config
  resources  = var.temporal_admin.resources
  units      = var.temporal_admin.units
}

module "minio" {
  source = "../modules/minio"

  app_name           = var.minio.app_name
  model_uuid         = var.model_uuid
  channel            = local.channels.minio
  revision           = var.minio.revision
  base               = var.minio.base
  config             = var.minio.config
  resources          = var.minio.resources
  storage_directives = var.minio.storage_directives
  units              = var.minio.units
}

### INTEGRATIONS

# Airbyte -> PostgreSQL (metadata database) and MinIO (object storage).
resource "juju_integration" "airbyte_db" {
  model_uuid = var.model_uuid

  application {
    name     = module.airbyte.app_name
    endpoint = module.airbyte.requires.db
  }
  dynamic "application" {
    for_each = [local.database_endpoint]
    content {
      name      = application.value.name
      endpoint  = application.value.endpoint
      offer_url = application.value.offer_url
    }
  }
}

resource "juju_integration" "airbyte_object_storage" {
  model_uuid = var.model_uuid

  application {
    name     = module.airbyte.app_name
    endpoint = module.airbyte.requires.object_storage
  }
  application {
    name     = module.minio.app_name
    endpoint = module.minio.provides.object_storage
  }
}

# Temporal -> PostgreSQL (default + visibility stores) and the admin charm.
# Airbyte reaches Temporal via the `temporal-host` config (default `temporal-k8s:7233`),
# not a relation, so no Airbyte<->Temporal integration is required here.
resource "juju_integration" "temporal_db" {
  model_uuid = var.model_uuid

  application {
    name     = module.temporal_k8s.app_name
    endpoint = module.temporal_k8s.requires.db
  }
  dynamic "application" {
    for_each = [local.database_endpoint]
    content {
      name      = application.value.name
      endpoint  = application.value.endpoint
      offer_url = application.value.offer_url
    }
  }
}

resource "juju_integration" "temporal_visibility" {
  model_uuid = var.model_uuid

  application {
    name     = module.temporal_k8s.app_name
    endpoint = module.temporal_k8s.requires.visibility
  }
  dynamic "application" {
    for_each = [local.database_endpoint]
    content {
      name      = application.value.name
      endpoint  = application.value.endpoint
      offer_url = application.value.offer_url
    }
  }
}

resource "juju_integration" "temporal_admin" {
  model_uuid = var.model_uuid

  application {
    name     = module.temporal_k8s.app_name
    endpoint = module.temporal_k8s.requires.admin
  }
  application {
    name     = module.temporal_admin_k8s.app_name
    endpoint = module.temporal_admin_k8s.provides.admin
  }
}

resource "juju_integration" "temporal_host_info" {
  model_uuid = var.model_uuid

  application {
    name     = module.temporal_k8s.app_name
    endpoint = module.temporal_k8s.provides.temporal_host_info
  }
  application {
    name     = module.temporal_admin_k8s.app_name
    endpoint = module.temporal_admin_k8s.provides.temporal_host_info
  }
}
