[![Charmhub Badge](https://charmhub.io/airbyte-k8s/badge.svg)](https://charmhub.io/airbyte-k8s)
[![Release Edge](https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml/badge.svg)](https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml)

**Charmed Airbyte K8s Operator** is an open-source, production-ready data integration platform operator for **Kubernetes**, that helps you deploy and manage [Airbyte](https://airbyte.io/).

Airbyte simplifies the process of **extracting and loading data** from various sources into a variety of destinations such as **data warehouses, data lakes, or data meshes**, enabling continuous, scheduled data synchronization to ensure data freshness and reliability.

The Charmed Airbyte K8s Operator automates the **deployment, configuration, and lifecycle management** of the Airbyte server on Kubernetes using **Juju**. It wraps the official Airbyte server distribution and integrates with other charms to form a complete data ingestion pipeline within the Canonical data ecosystem.

It is intended for **data engineers and platform teams** who want to automate and scale Airbyte deployments while maintaining consistency and observability across environments.

### Key Dependencies

| Requirement | Charm | Purpose |
| --- | --- | --- |
| **Database** | [`postgresql-k8s`](https://charmhub.io/postgresql-k8s) | Stores Airbyte metadata, job configurations, and sync history |
| **Workflow Engine** | [`temporal-k8s`](https://charmhub.io/temporal-k8s) | Manages task queues and workflow execution |
| **Object Storage** | [`minio`](https://charmhub.io/minio) or [`s3-integrator`](https://charmhub.io/s3-integrator) | Stores sync logs, state, and artifacts |

> Note: Either MinIO or S3 Integrator can be used as the object store; not both.

### Features

- Automated deployment and scaling on Kubernetes
- Seamless integration with PostgreSQL, Temporal, and object storage via Juju relations
- Simple Airbyte UI access for connector configuration and monitoring
- Ingress and authentication integration via Nginx and OAuth2 Proxy charms
- Observability through Juju relation-based configuration

### In this documentation

| Section | Description |
| --- | --- |
| **Tutorial** | A hands-on guide to deploying and configuring Charmed Airbyte for new users |
| **How-to guides** | Step-by-step instructions for common operational tasks, such as ingress, authentication, and upgrades |
| **Reference** | Technical details on configuration options, actions, and relations |

### Observability

The charm integrates with the [Canonical Observability Stack (COS)](https://charmhub.io/topics/canonical-observability-stack) over three relations:

- `logging` (`loki_push_api`) — forwards all Airbyte container logs to Loki.
- `grafana-dashboard` (`grafana_dashboard`) — provisions the **Airbyte** dashboard.
- `send-otlp` (`otlp`) — points Airbyte's Micrometer exporter at a related
  [opentelemetry-collector](https://charmhub.io/opentelemetry-collector-k8s)'s OTLP endpoint.

The provisioned dashboard is **log-based**: it derives health signals from the forwarded
logs (log-level and error trends, per-component activity, Temporal connectivity, plus
filtered-error and raw log panels).

**Metrics on the community edition.** The `send-otlp` metrics path is wired and correct,
but carries **no data on Airbyte's community edition** — community does not emit application
metrics over OTLP (native metrics are gated behind Airbyte Enterprise). The metrics activate
automatically on a metrics-enabled edition. Note that Airbyte's per-sync detail (records,
bytes, job status) is written to job logs (object storage) and exposed via the Airbyte API,
not the forwarded container stream — so surfacing sync/business metrics on community would
require a dedicated exporter rather than this pipeline.