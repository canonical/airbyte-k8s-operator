# Airbyte K8s product Terraform module

This folder contains a product [Terraform][Terraform] module that deploys `airbyte-k8s`
together with the dependencies it needs to run, and wires up the integrations between them.
It composes the base [charm module](../charm) and is a **reference** for how the charm can be
deployed — infrastructure-specific deployments (backends, ingress/TLS, SSO, external
databases) are expected to build on top of it.

## What it deploys

Into a single Kubernetes Juju model (`model_uuid`):

- **airbyte-k8s** — via the [charm module](../charm) (deployed with `trust`, which Airbyte
  needs to read and patch its auth secret).
- **postgresql-k8s** — the metadata database shared by Airbyte and Temporal.
- **temporal-k8s** + **temporal-admin-k8s** — Airbyte's workflow engine and its schema manager.
- **minio** — object storage for logs, state and workload output.

## Integrations

| From | To | Purpose |
| --- | --- | --- |
| `airbyte-k8s:db` | `postgresql-k8s:database` | Airbyte metadata database |
| `airbyte-k8s:object-storage` | `minio:object-storage` | Airbyte object storage |
| `temporal-k8s:db` | `postgresql-k8s:database` | Temporal default store |
| `temporal-k8s:visibility` | `postgresql-k8s:database` | Temporal visibility store |
| `temporal-k8s:admin` | `temporal-admin-k8s:admin` | Temporal schema management |
| `temporal-k8s:temporal-host-info` | `temporal-admin-k8s:temporal-host-info` | Admin CLI addressing |

Airbyte connects to Temporal through the `temporal-host` **config** (default
`temporal-k8s:7233`), not a relation, so there is no Airbyte↔Temporal integration.

## Module structure

- **main.tf** - Composes the charm module, deploys the dependencies, and wires the integrations.
- **variables.tf** - Per-application deployment options (channel, revision, base, config, units).
- **outputs.tf** - The model UUID and the deployed application names.
- **terraform.tf** - Terraform and provider version constraints.

## Usage

```text
module "airbyte" {
  source     = "git::https://github.com/canonical/airbyte-k8s-operator//terraform/product"
  model_uuid = var.model_uuid
  # (Override per-application channels/revisions/config as needed)
}
```

## External database

By default the module deploys `postgresql-k8s` in-model and relates Airbyte and Temporal to it.
To use an external database instead (e.g. a managed PostgreSQL on another controller), set
`database_offer_url` to a consumable `database` offer URL — then `postgresql-k8s` is not deployed
and the Airbyte and Temporal database relations point at the offer:

```text
module "airbyte" {
  source             = "git::https://github.com/canonical/airbyte-k8s-operator//terraform/product"
  model_uuid         = var.model_uuid
  database_offer_url = "controller:admin/db-model.postgresql"
}
```

## Notes

- **Object storage:** this module uses MinIO. To use AWS S3 instead, drop the `minio`
  application and its integration and relate `airbyte-k8s:s3-parameters` to an
  `s3-integrator`, setting the charm's `storage-type` config to `S3`.
- **Post-deploy step:** Temporal requires a default namespace, created via the
  `temporal-admin-k8s` `cli` action (`tctl ... namespace register`). Terraform does not run
  Juju actions, so run this once after `apply` for a fully functional stack.
- **Observability / ingress:** the optional `logging`, `grafana-dashboard`, `send-otlp` and
  `ingress` endpoints are left unwired here; relate them to COS and an ingress provider in a
  higher-level module.

[Terraform]: https://www.terraform.io/
