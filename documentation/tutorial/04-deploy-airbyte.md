
# Deploy Charmed Airbyte

This part of the tutorial explains how to deploy the Charmed Airbyte application and integrate it with its supporting components deployed in the previous step.

## 1. Deploy Charmed Airbyte

Deploy Airbyte using the official charm:
```bash
juju deploy airbyte-k8s --channel edge --trust
```

Verify the deployment:
```bash
juju status --watch 2s
```

Initially, Airbyte will be in a **blocked** state with a message such as:
```
database relation not ready
```
Relations will be added in the next steps.

## 2. Integrate Airbyte with MinIO (Object Storage)

Airbyte requires object storage for logs, artifacts, and state.

Add the relation between MinIO and Airbyte:
```bash
juju relate minio airbyte-k8s
```

Expected status after the relation settles:
```
airbyte-k8s/0: active | waiting for database connection
```

## 3. Integrate Airbyte with PostgreSQL (Metadata Database)

Airbyte depends on PostgreSQL to store metadata, configuration, and job history.

Add the relation between PostgreSQL and Airbyte:
```bash
juju relate postgresql-k8s airbyte-k8s
```

Airbyte will transition to a new blocked state until Temporal is related:
```
temporal relation not ready
```

## 4. Integrate Airbyte with Temporal (Workflow Engine)

Airbyte depends on two Temporal charms:
* `temporal-k8s` — the Temporal workflow engine
* `temporal-admin-k8s` — provides UI and admin capabilities

Add the relations:
```bash
juju relate temporal-k8s:db postgresql-k8s:database
juju relate temporal-k8s:visibility postgresql-k8s:database
juju relate temporal-k8s:admin temporal-admin-k8s:admin
```

After all relations and configurations are applied:

```bash
juju status
```

All applications (`airbyte-k8s`, `temporal-k8s`, `temporal-admin-k8s`, `postgresql-k8s`, `minio`) should eventually show `active` status. At this point, Airbyte is fully operational.

## Next steps

[Secure Airbyte deployments](../how-to/secure-airbyte-deployments.md)