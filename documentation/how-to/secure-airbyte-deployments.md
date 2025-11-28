# Secure Airbyte Deployments

This guide explains how to configure security, authentication, ingress, and webhook features for a Charmed Airbyte deployment.

## Terminate TLS at Ingress

Airbyte can terminate Transport Layer Security (TLS) at the ingress using the [Nginx Ingress Integrator Charm](https://charmhub.io/nginx-ingress-integrator).

Deploy it:

```bash
juju deploy nginx-ingress-integrator --trust
```

## Manage TLS Certificates with Lego

Airbyte can automatically provision and renew TLS certificates with [Lego](https://charmhub.io/lego).

1. Deploy the Lego charm:

```bash
juju deploy lego --trust
```

2. Configure the charm:

```bash
juju config lego \
  plugin="your-plugin" \
  email="your-email@example.com" \
  plugin-config-secret-id="your-secret-id"
```

3. Grant Lego access to secrets:

```bash
juju add-access-secret lego --applications=lego --secret-id=your-secret-id
```

4. Relate Lego to your ingress integrator:

```bash
juju relate lego nginx-ingress-integrator
```

5. Validate certificate requests:

```bash
juju status lego
```

> Look for `1/1 certificate requests are fulfilled` to confirm active TLS certificates.

### Using Kubernetes Secrets

Alternatively, you can provide your own TLS certificates via Kubernetes secrets:

```bash
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=<YOUR_HOSTNAME>"
openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt -extfile <(printf "subjectAltName=DNS:<YOUR_HOSTNAME>")
kubectl create secret tls airbyte-tls --cert=server.crt --key=server.key
```

Configure Airbyte to use this secret:

```bash
juju config airbyte-k8s tls-secret-name=airbyte-tls
juju config airbyte-k8s external-hostname=<YOUR_HOSTNAME>
```

Relate Airbyte to the ingress integrator:

```bash
juju relate airbyte-k8s nginx-ingress-integrator
```

Validate ingress:

```bash
kubectl get ingress
kubectl describe ingress <YOUR_INGRESS_NAME>
```

## Enable OAuth2 Authentication

Airbyte supports OAuth2 via [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/), allowing login with providers such as Google.

### Obtain OAuth2 Credentials

1. Navigate to your provider’s developer console (e.g., Google Cloud).
2. Create a new OAuth2 client ID for a web application.
3. Add an Authorized Redirect URI in the format:

```
https://<host>/oauth2/callback
```

4. Save the client ID and secret.

### Apply OAuth2 Configuration

Create `oauth.yaml`:

```yaml
oauth2-proxy-k8s:
  client-id: "<client_id>"
  client-secret: "<client_secret>"
  cookie-secret: "<cookie_secret>"
  external-hostname: "<your-hostname>"
  authenticated-emails-list: "<emails>"
```

Apply the configuration:

```bash
juju config oauth2-proxy-k8s --file=oauth.yaml
```

Relate the proxy to ingress:

```bash
juju relate oauth2-proxy-k8s nginx-ingress-integrator
```

## Configure Airbyte Webhooks

Use the [airbyte-webhooks-k8s](https://charmhub.io/airbyte-webhooks-k8s) charm for secure webhook access. Relate it to a dedicated ingress:

```bash
juju relate airbyte-webhooks-k8s nginx-ingress-integrator-airbyte-webhooks
```

> Webhooks can be used to trigger pipelines or notifications securely.