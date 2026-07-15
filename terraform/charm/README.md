# Airbyte K8s charm Terraform module

This folder contains a base [Terraform][Terraform] module for the `airbyte-k8s` charm.

The module uses the [Terraform Juju provider][Terraform Juju provider] to model the charm
deployment onto any Kubernetes environment managed by Juju. It models the `airbyte-k8s`
application only; its dependencies (PostgreSQL, Temporal, object storage, ingress,
observability) are wired up by a higher-level product module.

## Module structure

- **main.tf** - Defines the `airbyte-k8s` Juju application.
- **variables.tf** - Deployment options (model UUID, channel, revision, config, resources, …).
- **outputs.tf** - The application name and the `provides`/`requires` integration endpoints.
- **terraform.tf** - Terraform and provider version constraints.

## Using `airbyte-k8s` base module in higher level modules

```text
module "airbyte" {
  source     = "git::https://github.com/canonical/airbyte-k8s-operator//terraform/charm"
  model_uuid = var.model_uuid
  # (Customize configuration variables here if needed)
}
```

Create integrations, for instance against PostgreSQL:

```text
resource "juju_integration" "airbyte_db" {
  model_uuid = var.model_uuid
  application {
    name     = module.airbyte.app_name
    endpoint = module.airbyte.requires.db
  }
  application {
    name     = "postgresql-k8s"
    endpoint = "database"
  }
}
```

The complete list of available integrations can be found [in the Integrations tab][airbyte-integrations].

[Terraform]: https://www.terraform.io/
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
[airbyte-integrations]: https://charmhub.io/airbyte-k8s/integrations
