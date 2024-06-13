# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://juju.is/docs/sdk/dev-setup).

First, install the required version of `tox`:

```shell
pip install -r dev-requirements.txt
```

You can create an environment for development with `tox`:

```shell
tox devenv -e integration
source venv/bin/activate
```

## Testing

This project uses `tox` for managing test environments. There are some
pre-configured environments that can be used for linting and formatting code
when you're preparing contributions to the charm:

```shell
tox run -e format        # update your code according to linting rules
tox run -e lint          # code style
tox run -e static        # static type checking
tox run -e unit          # unit tests
tox run -e integration   # integration tests
tox                      # runs 'format', 'lint', 'static', and 'unit' environments
```

### Committing

This repo uses CI/CD workflows as outlined by
[operator-workflows](https://github.com/canonical/operator-workflows). The four
workflows are as follows:

- `test.yaml`: This is a series of tests including linting, unit tests and
  library checks which run on every pull request.
- `integration_test.yaml`: This runs the suite of integration tests included
  with the charm and runs on every pull request.
- `test_and_publish_charm.yaml`: This runs either by manual dispatch or on every
  push to the main branch or a special track/\*\* branch. Once a PR is merged
  with one of these branches, this workflow runs to ensure the tests have passed
  before building the charm and publishing the new version to the edge channel
  on Charmhub.
- `promote_charm.yaml`: This is a manually triggered workflow which publishes
  the charm currently on the edge channel to the stable channel on Charmhub.

These tests validate extensive linting and formatting rules. Before creating a
PR, please run `tox` to ensure proper formatting and linting is performed.

### Deploy

This charm is used to deploy Airbyte server in a k8s cluster. For a local
deployment, follow the following steps:

#### Install Microk8s

```bash
# Install Microk8s from snap
sudo snap install microk8s --classic --channel=1.25

# Install charmcraft from snap
sudo snap install charmcraft --classic

# Add the 'ubuntu' user to the Microk8s group
sudo usermod -a -G microk8s ubuntu

# Give the 'ubuntu' user permissions to read the ~/.kube directory
sudo chown -f -R ubuntu ~/.kube

# Create the 'microk8s' group
newgrp microk8s

# Enable the necessary Microk8s addons
microk8s enable hostpath-storage dns
```

#### Set up the Juju OLM

```bash
# Install the Juju CLI client, juju. Minimum version required is juju>=3.1.
sudo snap install juju --classic

# Install a "juju" controller into your "microk8s" cloud
juju bootstrap microk8s airbyte-controller

# Create a 'model' on this controller
juju add-model airbyte

# Enable DEBUG logging
juju model-config logging-config="<root>=INFO;unit=DEBUG"

# Check progress
juju status --relations --watch 2s
juju debug-log
```

#### Deploy Charm

```bash
# Pack the charm
charmcraft pack # the --destructive-mode flag can be used to pack the charm using the current host.

# Deploy the charm
juju deploy ./airbyte-k8s_ubuntu-22.04-amd64.charm --resource airbyte-api-server=airbyte/airbyte-api-server:0.60.0 --resource airbyte-bootloader=airbyte/bootloader:0.60.0 --resource airbyte-connector-builder-server=airbyte/connector-builder-server:0.60.0 --resource airbyte-cron=airbyte/cron:0.60.0 --resource airbyte-pod-sweeper=bitnami/kubectl:1.29.4 --resource airbyte-server=airbyte/server:0.60.0 --resource airbyte-worker=airbyte/worker:0.60.0

# Deploy ui charm (Only if modifying UI charm, otherwise deploy using `juju deploy airbyte-ui-k8s --channel edge`)
juju deploy ./airbyte-ui-k8s_ubuntu-22.04-amd64.charm --resource airbyte-webapp=airbyte/webapp:0.60.0
```

#### Relate Charms

```bash
# Relate operator to postgresql
juju deploy postgresql-k8s --channel 14/edge --trust
juju relate airbyte-k8s postgresql-k8s

# Relate operator to minio
juju deploy minio --channel edge
juju relate airbyte-k8s minio

# Deploy Temporal operators
juju deploy temporal-k8s
juju deploy temporal-admin-k8s
juju relate temporal-k8s:db postgresql-k8s:database
juju relate temporal-k8s:visibility postgresql-k8s:database
juju relate temporal-k8s:admin temporal-admin-k8s:admin

# Wait for units to settle and create default namespace
juju run temporal-admin-k8s/0 tctl args="--ns default namespace register -rd 3"

# Relate to Airbyte ui operator
juju relate airbyte-k8s airbyte-ui-k8s

# Generate private key
openssl genrsa -out airbyte.key 2048

# Generate a certificate signing request
openssl req -new -key airbyte.key -out airbyte.csr -subj "/CN=airbyte-k8s"

# Create self-signed certificate
openssl x509 -req -days 365 -in airbyte.csr -signkey airbyte.key -out airbyte.crt -extfile <(printf "subjectAltName=DNS:airbyte-k8s")

# Create a k8s secret
kubectl create secret tls airbyte-tls --cert=airbyte.crt --key=airbyte.key

# Deploy ingress controller
microk8s enable ingress:default-ssl-certificate=airbyte/airbyte-tls

# Deploy nginx operator
juju deploy nginx-ingress-integrator --channel edge
juju relate airbyte-ui-k8s nginx-ingress-integrator
```

#### Cleanup

```bash
# Clean-up before retrying
# Either remove individual applications 
# (The --force flag can optionally be included if any of the units are in error state)
juju remove-application airbyte-k8s
juju remove-application airbyte-ui-k8s
juju remove-application postgresql-k8s --destroy-storage
juju remove-application minio
juju remove-application nginx-ingress-integrator

# Or remove whole model
juju destroy-model airbyte --destroy-storage
```
