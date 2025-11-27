# Deploy Supporting Charms

This part of the tutorial focuses on deploying supporting charms that Airbyte requires for metadata storage, workflow orchestration, and object storage.

| Requirement         | Charm                                                                      | Purpose                                               |
| ------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------- |
| **Database**        | [`postgresql-k8s`](https://charmhub.io/postgresql-k8s)                     | Stores metadata, job configurations, and sync history |
| **Workflow Engine** | [`temporal-k8s`](https://charmhub.io/temporal-k8s)                         | Manages task queues and workflow execution            |
| **Admin UI**        | [`temporal-admin-k8s`](https://charmhub.io/temporal-admin-k8s)             | Manages Temporal namespaces and admin tasks           |
| **Object Storage**  | [`minio`](https://charmhub.io/minio) or S3 Integrator                      | Stores sync logs, state, and artifacts                |
| **Ingress**         | [`nginx-ingress-integrator`](https://charmhub.io/nginx-ingress-integrator) | Provides TLS termination and routing                  |
| **TLS Management**  | [`lego`](https://charmhub.io/lego)                                         | Auto-provisions TLS certificates for ingress          |

> Note: Either MinIO or S3 Integrator can be used; not both.

## Deploy PostgreSQL

```bash
juju deploy postgresql-k8s --channel 14/edge --trust
juju status --watch 2s
```

> Deployment may take ~10 minutes. Expect `active` status for all units once complete.

## Deploy MinIO

```bash
juju deploy minio --channel edge
juju status --watch 2s
```

> Deployment completes when all units are `active`.

## Deploy Temporal

```bash
juju deploy temporal-k8s --config num-history-shards=4
juju deploy temporal-admin-k8s
juju status --watch 2s
```

> Temporal requires `num-history-shards` to be a power of 2.

Ignore temporary `blocked` messages; they will be resolved once relations are added in the next step.

## Deploy Nginx Ingress Integrator

```bash
juju deploy nginx-ingress-integrator --trust
juju status --watch 2s
```

## Deploy Lego for TLS Certificates

```bash
juju deploy lego --trust
juju config lego plugin="your-plugin" email="your-email" plugin-config-secret-id="your-secret-id"
```

**See next: 
[Deploy Charmed Airbyte](./04-deploy-airbyte.md)**