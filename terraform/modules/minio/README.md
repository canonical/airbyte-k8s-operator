# MinIO charm Terraform module

This folder contains a base [Terraform][Terraform] module for the `minio` charm.

The module uses the [Terraform Juju provider][Terraform Juju provider] to model the charm
deployment onto any Kubernetes environment managed by Juju. It models the `minio`
application only; integrations with consumers (e.g. Airbyte object storage) are wired up by a
higher-level product module.

## Module structure

- **main.tf** - Defines the `minio` Juju application.
- **variables.tf** - Deployment options (model UUID, channel, revision, config, resources, …).
- **outputs.tf** - The application name/resource and the `provides` integration endpoints.
- **terraform.tf** - Terraform and provider version constraints.

## Inputs

| Name                 | Type          | Default          | Description                                              |
| -------------------- | ------------- | ---------------- | -------------------------------------------------------- |
| `app_name`           | `string`      | `"minio"`        | Name of the application in the Juju model.               |
| `base`               | `string`      | `"ubuntu@24.04"` | The operating system on which to deploy.                 |
| `channel`            | `string`      | `"1.10/stable"`  | The channel to use when deploying the charm.             |
| `config`             | `map(string)` | `{}`             | Application configuration.                               |
| `constraints`        | `string`      | `null`           | Juju constraints to apply to the application.            |
| `model_uuid`         | `string`      | (required)       | UUID of the Juju model to deploy into.                   |
| `resources`          | `map(string)` | `{}`             | OCI-image resources to use instead of the bundled ones.  |
| `revision`           | `number`      | `null`           | Charm revision to deploy (`null` = latest on channel).   |
| `storage_directives` | `map(string)` | `{}`             | Storage directives for the application.                  |
| `units`              | `number`      | `1`              | Number of units to deploy.                               |

## Outputs

| Name          | Type          | Description                                            |
| ------------- | ------------- | ----------------------------------------------------- |
| `app_name`    | `string`      | Name of the deployed application.                     |
| `application` | `object`      | The deployed application resource.                    |
| `provides`    | `map(string)` | Map of the charm's `provides` integration endpoints.  |

## Using the `minio` base module in higher level modules

```text
module "minio" {
  source     = "git::https://github.com/canonical/airbyte-k8s-operator//terraform/modules/minio"
  model_uuid = var.model_uuid
  # (Customize configuration variables here if needed)
}
```

The complete list of available integrations can be found [in the Integrations tab][minio-integrations].

[Terraform]: https://www.terraform.io/
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
[minio-integrations]: https://charmhub.io/minio/integrations
