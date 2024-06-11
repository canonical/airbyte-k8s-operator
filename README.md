# Airbyte K8s Operator

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

### Deploying PostgreSQL Database

The Airbyte and PostgreSQL operators can be deployed and connected to each
other using the Juju command line as follows:

```bash
juju deploy airbyte-k8s --trust
juju deploy postgresql-k8s --channel 14/edge --trust
juju relate airbyte-k8s postgresql-k8s
```

### Deploying Minio

The Airbyte and Minio operators can be deployed and connected to each
other using the Juju command line as follows:

```bash
juju deploy minio --channel edge
juju relate airbyte-k8s minio
```

### Deploying Temporal

The Temporal operators can be deployed and connected to each
other using the Juju command line as follows:

```bash
juju deploy temporal-k8s
juju deploy temporal-admin-k8s
juju relate temporal-k8s:db postgresql-k8s:database
juju relate temporal-k8s:visibility postgresql-k8s:database
juju relate temporal-k8s:admin temporal-admin-k8s:admin
```

Once the units have settled, the following command can be run to create the default namespace:

```bash
juju run temporal-admin-k8s/0 tctl args="--ns default namespace register -rd 3"
```


### Deploying Airbyte UI

To configure connectors through the web UI, the Airbyte operator requires
integration with the
[Airbyte UI operator](https://github.com/canonical/airbyte-ui-k8s-operator).
Once the Airbyte UI operator is deployed, it can be connected to the Airbyte
operator using the Juju command line as follows:

```bash
juju deploy airbyte-ui-k8s
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
[CONTRIBUTING.md](./CONTRIBUTING.md) for developer guidance.
