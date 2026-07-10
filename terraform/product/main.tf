# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

### AIRBYTE (via the base charm module)

module "airbyte" {
  source = "../charm"

  app_name    = var.airbyte.app_name
  model_uuid  = var.model_uuid
  channel     = var.airbyte.channel
  revision    = var.airbyte.revision
  base        = var.airbyte.base
  config      = var.airbyte.config
  constraints = var.airbyte.constraints
  resources   = var.airbyte.resources
  trust       = var.airbyte.trust
  units       = var.airbyte.units
}

### DEPENDENCIES

resource "juju_application" "postgresql_k8s" {
  count      = local.deploy_database ? 1 : 0
  name       = var.postgresql.app_name
  model_uuid = var.model_uuid
  trust      = true

  charm {
    name     = "postgresql-k8s"
    channel  = var.postgresql.channel
    revision = var.postgresql.revision
    base     = var.postgresql.base
  }

  config             = var.postgresql.config
  constraints        = var.postgresql.constraints
  storage_directives = var.postgresql.storage_directives
  units              = var.postgresql.units
}

resource "juju_application" "temporal_k8s" {
  name       = var.temporal.app_name
  model_uuid = var.model_uuid

  charm {
    name     = "temporal-k8s"
    channel  = var.temporal.channel
    revision = var.temporal.revision
    base     = var.temporal.base
  }

  config = var.temporal.config
  units  = var.temporal.units
}

resource "juju_application" "temporal_admin_k8s" {
  name       = var.temporal_admin.app_name
  model_uuid = var.model_uuid

  charm {
    name     = "temporal-admin-k8s"
    channel  = var.temporal_admin.channel
    revision = var.temporal_admin.revision
    base     = var.temporal_admin.base
  }

  units = var.temporal_admin.units
}

resource "juju_application" "minio" {
  name       = var.minio.app_name
  model_uuid = var.model_uuid

  charm {
    name     = "minio"
    channel  = var.minio.channel
    revision = var.minio.revision
    base     = var.minio.base
  }

  config             = var.minio.config
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
    name     = juju_application.minio.name
    endpoint = "object-storage"
  }
}

# Temporal -> PostgreSQL (default + visibility stores) and the admin charm.
# Airbyte reaches Temporal via the `temporal-host` config (default `temporal-k8s:7233`),
# not a relation, so no Airbyte<->Temporal integration is required here.
resource "juju_integration" "temporal_db" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.temporal_k8s.name
    endpoint = "db"
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
    name     = juju_application.temporal_k8s.name
    endpoint = "visibility"
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
    name     = juju_application.temporal_k8s.name
    endpoint = "admin"
  }
  application {
    name     = juju_application.temporal_admin_k8s.name
    endpoint = "admin"
  }
}

resource "juju_integration" "temporal_host_info" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.temporal_k8s.name
    endpoint = "temporal-host-info"
  }
  application {
    name     = juju_application.temporal_admin_k8s.name
    endpoint = "temporal-host-info"
  }
}
