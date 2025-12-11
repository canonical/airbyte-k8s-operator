# Pick namespace used by your model (default in your setup is "airbyte")
NS=airbyte

# Generate values
ID=$(uuidgen)
SECRET=$(openssl rand -hex 32)

# Create the secret with the expected keys
kubectl -n "$NS" create secret generic airbyte-auth-secrets \
  --from-literal=dataplane-client-id="$ID" \
  --from-literal=dataplane-client-secret="$SECRET"

# Verify
kubectl -n "$NS" get secret airbyte-auth-secrets -o yaml

juju trust airbyte-k8s --scope=cluster