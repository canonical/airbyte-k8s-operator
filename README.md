[![Charmhub Badge](https://charmhub.io/airbyte-k8s/badge.svg)](https://charmhub.io/airbyte-k8s)
[![Release Edge](https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml/badge.svg)](https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml)

# Airbyte Server

This is the Kubernetes Python Operator for [Airbyte](https://airbyte.com/).

## Description

Airbyte is an open-source data integration platform designed to centralize and
streamline the process of extracting and loading data from various sources into
data warehouses, lakes, or other destinations.

This operator provides an Airbyte server, and consists of Python scripts which
wraps the versions distributed by
[Airbyte](https://hub.docker.com/r/airbyte/server).

## Usage

Note: This operator requires the use of juju>=3.1.

The Airbyte charm relies on a number of other charms for core functionality.
Below is a set of requirements and the charms that fulfill them:

- Database: [Postgresql-k8s](https://charmhub.io/postgresql-k8s)
- Workflow Engine: [Temporal-k8s](https://charmhub.io/temporal-k8s)
- Object Storage: a. [Minio](https://charmhub.io/minio) b.
  [S3 integrator](https://charmhub.io/s3-integrator)

Note: For object storage, the use of one of the Minio or S3 integrator charm is
sufficient.

### Deploying PostgreSQL Database

Airbyte uses PostgreSQL for storing metadata. The Airbyte and PostgreSQL
operators can be deployed and connected to each other using the Juju command
line as follows:

```bash
juju deploy airbyte-k8s --channel edge --trust
juju deploy postgresql-k8s --channel 14/edge --trust
juju relate airbyte-k8s postgresql-k8s
```

Note: The `--trust` is required when deploying charmed Airbyte k8s to enable it
to create k8s pods for sync jobs. The charm contains a script which periodically
cleans up these resources once they complete their function.

### Deploying Minio

Airbyte uses Minio for storing state and relevant logs. The Airbyte and Minio
operators can be deployed and connected to each other using the Juju command
line as follows:

```bash
juju deploy minio --channel edge
juju relate airbyte-k8s minio
```

### Deploying Temporal

Airbyte uses Temporal as a workflow engine for durable execution of sync jobs.
The Temporal operators can be deployed and connected to each other using the
Juju command line as follows:

```bash
juju deploy temporal-k8s --config num-history-shards=4 # This value can be increased to 1024 or 2048 for a production deployment
juju deploy temporal-admin-k8s
juju relate temporal-k8s:db postgresql-k8s:database
juju relate temporal-k8s:visibility postgresql-k8s:database
juju relate temporal-k8s:admin temporal-admin-k8s:admin
```

Once the units have settled, the following command can be run to create the
default namespace:

```bash
juju run temporal-admin-k8s/0 tctl args="--ns default namespace register -rd 3"
```

The Airbyte charm is configured by default to connect to the Temporal charm at
`temporal-k8s:7233`, so no further action is needed here.

### Deploying Airbyte UI

To configure connectors through the web UI, the Airbyte operator requires
integration with the
[Airbyte UI operator](https://github.com/canonical/airbyte-ui-k8s-operator).
Once the Airbyte UI operator is deployed, it can be connected to the Airbyte
operator using the Juju command line as follows:

```bash
juju deploy airbyte-ui-k8s --channel edge
juju relate airbyte-k8s airbyte-ui-k8s
```

You should now be able to access the web UI at `<airbyte_ui_unit_ip>:8080`.

## Verifying

To verify that the setup is running correctly, run
`juju status --relations --watch 2s` and ensure that all pods are active and all
required integrations exist.

## Contributing

This charm is still in active development. Please see the
[Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/airbyte-k8s-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

test
