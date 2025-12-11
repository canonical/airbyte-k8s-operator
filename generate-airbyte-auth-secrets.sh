# Pick namespace used by your model (default in your setup is "airbyte")
NS=airbyte-2

# Generate values
ID=$(uuidgen)
SECRET=$(openssl rand -hex 32)

# Create the secret with the expected keys
microk8s.kubectl -n "$NS" create secret generic airbyte-auth-secrets \
  --from-literal=dataplane-client-id="$ID" \
  --from-literal=dataplane-client-secret="$SECRET"

# Verify
microk8s.kubectl -n "$NS" get secret airbyte-auth-secrets -o yaml

juju trust airbyte-k8s --scope=cluster
