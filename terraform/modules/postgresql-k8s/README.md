# PostgreSQL K8s charm Terraform module

This folder contains a base [Terraform][Terraform] module for the `postgresql-k8s` charm.

The module uses the [Terraform Juju provider][Terraform Juju provider] to model the charm
deployment onto any Kubernetes environment managed by Juju. It models the `postgresql-k8s`
application only; integrations with consumers are wired up by a higher-level product module.

## Module structure

- **main.tf** - Defines the `postgresql-k8s` Juju application.
- **variables.tf** - Deployment options (model UUID, channel, revision, config, resources, …).
- **outputs.tf** - The application name/resource and the `provides` integration endpoints.
- **terraform.tf** - Terraform and provider version constraints.

## Inputs

| Name                 | Type          | Default             | Description                                              |
| -------------------- | ------------- | ------------------- | -------------------------------------------------------- |
| `app_name`           | `string`      | `"postgresql-k8s"`  | Name of the application in the Juju model.               |
| `base`               | `string`      | `"ubuntu@22.04"`    | The operating system on which to deploy.                 |
| `channel`            | `string`      | `"14/stable"`       | The channel to use when deploying the charm.             |
| `config`             | `map(string)` | `{}`                | Application configuration.                               |
| `constraints`        | `string`      | `null`              | Juju constraints to apply to the application.            |
| `model_uuid`         | `string`      | (required)          | UUID of the Juju model to deploy into.                   |
| `resources`          | `map(string)` | `{}`                | OCI-image resources to use instead of the bundled ones.  |
| `revision`           | `number`      | `null`              | Charm revision to deploy (`null` = latest on channel).   |
| `storage_directives` | `map(string)` | `{}`                | Storage directives for the application.                  |
| `units`              | `number`      | `1`                 | Number of units to deploy.                               |

## Outputs

| Name          | Type          | Description                                            |
| ------------- | ------------- | ----------------------------------------------------- |
| `app_name`    | `string`      | Name of the deployed application.                     |
| `application` | `object`      | The deployed application resource.                    |
| `provides`    | `map(string)` | Map of the charm's `provides` integration endpoints.  |

## Using the `postgresql-k8s` base module in higher level modules

```text
module "postgresql_k8s" {
  source     = "git::https://github.com/canonical/airbyte-k8s-operator//terraform/modules/postgresql-k8s"
  model_uuid = var.model_uuid
  # (Customize configuration variables here if needed)
}
```

The complete list of available integrations can be found [in the Integrations tab][postgresql-integrations].

[Terraform]: https://www.terraform.io/
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
[postgresql-integrations]: https://charmhub.io/postgresql-k8s/integrations
