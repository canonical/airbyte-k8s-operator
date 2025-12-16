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
tox run -e fmt        # update your code according to linting rules
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
- `publish_charm.yaml`: This runs either by manual dispatch or on every
  push to the main branch. Once a PR is merged
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


#### Install Rockcraft

```bash
sudo snap install rockcraft --edge --classic
sudo snap install lxd
lxd init --auto

# Note: Docker must be installed after LXD is initialized due to firewall rules incompatibility.
sudo snap install docker
sudo groupadd docker
sudo usermod -aG docker $USER
newgrp docker

# Note: disabling and enabling docker snap is required to avoid sudo requirement. 
# As described in https://github.com/docker-snap/docker-snap.
sudo snap disable docker
sudo snap enable docker
```

#### Install Microk8s

```bash
# Install charmcraft from snap
sudo snap install charmcraft --channel latest/edge --classic

# Install Microk8s from snap
sudo snap install microk8s --channel 1.32-strict/stable

# Add your user to MicroK8s group and refresh session
sudo adduser $USER snap_microk8s
sudo chown -R $USER ~/.kube # -- chown: cannot access '/home/ubuntu/.kube': No such file or directory
newgrp snap_microk8s

# Enable the necessary Microk8s addons
sudo microk8s enable rbac
sudo microk8s enable hostpath-storage
sudo microk8s enable dns
sudo microk8s enable registry
sudo microk8s enable ingress
```

#### Set up the Juju OLM

```bash
# Install the Juju CLI client, juju. Minimum version required is juju>=3.1.
sudo snap install juju --channel 3.6/stable
mkdir -p ~/.local/share

# Install a "juju" controller into your "microk8s" cloud
juju bootstrap microk8s airbyte-controller

# Create a 'model' on this controller
juju add-model airbyte
juju set-model-constraints -m airbyte arch=$(dpkg --print-architecture)

# Enable DEBUG logging
juju model-config logging-config="<root>=INFO;unit=DEBUG"

# Check progress
juju status --relations --watch 2s
juju debug-log
```


#### Packing the Rock

**Preferred: destructive-mode (no nested containers)**

To reliably build the Airbyte rock, use Rockcraft’s destructive-mode so the build runs on the host instead of inside LXD. This avoids Testcontainers/cgroup issues during Gradle’s jOOQ code generation.

Requirements when using destructive-mode:
- Host Ubuntu version should match the rock base in `airbyte_rock/rockcraft.yaml` (currently `ubuntu@22.04`). Building on a different series can cause toolchain/package mismatches.
- Root privileges (sudo) on the build machine.
- Sufficient resources: at least 4 CPU cores and 16 GB RAM are recommended. Rock builds compile multiple components (server, workers, UI) and run Gradle tasks that are memory/CPU intensive.

Example (native host matching base, e.g., Ubuntu 22.04):

```bash
cd airbyte_rock
sudo rockcraft pack --destructive-mode --verbose
```

**Multipass users (arm64 on Apple Silicon, etc.)**

- Do NOT build from a host-mounted directory inside the VM (e.g., a folder under `/home/ubuntu` that is mounted from the host). umoci will fail with `lchown permission denied` when unpacking the base.
- Instead, clone the repository directly inside the VM (or copy it to a native, non-mounted path), and run destructive-mode there. Running under `/root` is the most reliable:

```bash
# inside the Multipass VM
git clone https://github.com/canonical/airbyte-k8s-operator.git /root/work/airbyte-k8s-operator
cd /root/work/airbyte-k8s-operator/airbyte_rock
sudo rockcraft pack --destructive-mode --verbose
```

#### Upload Rock to registry
The rock needs to be copied to the Microk8s registry so that it can be deployed in the Kubernetes cluster:

```bash
rockcraft.skopeo --insecure-policy copy --dest-tls-verify=false oci-archive:airbyte_1.7.0_$(dpkg --print-architecture).rock docker://localhost:32000/airbyte:1.7.0
```

#### Deploy Charm

```bash
# Go to root directory of the project
cd ..

# Pack the charm
charmcraft pack # the --destructive-mode flag can be used to pack the charm using the current host.

# Deploy the charm
juju deploy ./airbyte-k8s_ubuntu-22.04-$(dpkg --print-architecture).charm --resource airbyte-image=localhost:32000/airbyte:1.7.0 --constraints='arch=arm64'
# add the following constraints if your cpu architecture is arm64:  --constraints='arch=arm64'

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

# Generate private key
openssl genrsa -out airbyte.key 2048

# Generate a certificate signing request
openssl req -new -key airbyte.key -out airbyte.csr -subj "/CN=airbyte-k8s"

# Create self-signed certificate
openssl x509 -req -days 365 -in airbyte.csr -signkey airbyte.key -out airbyte.crt -extfile <(printf "subjectAltName=DNS:airbyte-k8s")

# Create a k8s secret
kubectl -n airbyte create secret tls airbyte-tls --cert=airbyte.crt --key=airbyte.key

# Deploy ingress controller
microk8s enable ingress:default-ssl-certificate=airbyte/airbyte-tls

# Deploy nginx operator
juju deploy nginx-ingress-integrator --channel edge
juju trust nginx-ingress-integrator --scope=cluster
juju relate airbyte-ui-k8s nginx-ingress-integrator
```

#### Refreshing the Charm
```bash
# When we change the charm
charmcraft pack
juju refresh airbyte-k8s --path ./airbyte-k8s_ubuntu-22.04-$(dpkg --print-architecture).charm --resource airbyte-image=localhost:32000/airbyte:1.7.1

```

#### Cleanup

```bash
# Clean-up before retrying
# Either remove individual applications 
# (The --force flag can optionally be included if any of the units are in error state)
juju remove-application airbyte-k8s
juju remove-application postgresql-k8s --destroy-storage
juju remove-application minio
juju remove-application nginx-ingress-integrator

# Or remove whole model
juju destroy-model airbyte --destroy-storage
```
