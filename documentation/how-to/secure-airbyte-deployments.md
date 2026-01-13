# Enable security features

This guide describes the implementation of security features such as encryption and authentication.

## Terminate TLS at ingress

Airbyte can terminate Transport Layer Security (TLS) at the ingress by leveraging the [Nginx Ingress Integrator Charm](https://charmhub.io/nginx-ingress-integrator).

Deploy this by running:

```bash
juju deploy nginx-ingress-integrator --trust
```

### Using K8s secrets

You can use a self-signed or production-grade TLS certificate stored in a Kubernetes secret. The secret is then associated with the ingress to encrypt traffic between clients and Airbyte.

For self-signed certificates you can do the following:

1. First generate a private key using `openssl` and a certificate signing request using the key you just created. Replace `<YOUR_HOSTNAME>` with an appropriate hostname such as `airbyte-k8s.com`:

   ```bash
   openssl genrsa -out server.key 2048
   openssl req -new -key server.key -out server.csr -subj "/CN=<YOUR_HOSTNAME>"
   ```

2. You can now sign this signing request, creating your self-signed certificate:

   ```bash
   openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt -extfile <(printf "subjectAltName=DNS:<YOUR_HOSTNAME>")
   ```

3. Next, add this certificate and key as a Kubernetes secret to be used by the ingress:

   ```bash
   kubectl create secret tls airbyte-tls --cert=server.crt --key=server.key
   ```

4. You then need to provide the name of the Kubernetes secret to the Airbyte charm, along with the hostname you included in the certificate:

   ```bash
   juju config airbyte-k8s tls-secret-name=airbyte-tls
   juju config airbyte-k8s external-hostname=<YOUR_HOSTNAME>
   ```

5. Finally, relate Airbyte with the Nginx Ingress Integrator to create your ingress resource:

   ```bash
   juju relate airbyte-k8s nginx-ingress-integrator
   ```

**Note:** If you have a production-grade certificate, skip to step 3.

Validate your ingress has been created with the TLS certificates:

```bash
kubectl get ingress
kubectl describe <YOUR_INGRESS_NAME>
```

The ingress has the format `<relation_num>-<hostname>-ingress`. The `describe` command should show something similar to the below, with the Kubernetes secret you configured in `TLS`:

```text
Name:             relation-201-airbyte-k8s-com-ingress
Labels:           app.juju.is/created-by=nginx-ingress-integrator
                  nginx-ingress-integrator.charm.juju.is/managed-by=nginx-ingress-integrator
Namespace:        airbyte-model
Address:          <list-of-ips>
Ingress Class:    nginx-ingress-controller
Default backend:  <default>
TLS:
  airbyte-tls terminates airbyte-k8s.com
```

## Enable Google OAuth

Enabling Google OAuth for Charmed Airbyte allows users to authenticate using their Google accounts, streamlining login and increasing security. Google OAuth is handled by the `oauth2-proxy-k8s` charm, which sits in front of Airbyte and is exposed through `nginx-ingress-integrator`.

### Deploy OAuth2 Proxy

First, deploy the OAuth2 Proxy charm:

```bash
juju deploy oauth2-proxy-k8s --channel stable
```

### Obtain OAuth2 credentials

If you do not already have OAuth2 credentials set up, follow the steps below:

1. Navigate to https://console.cloud.google.com/apis/credentials.
2. Click `+ Create Credentials`.
3. Select `OAuth client ID`.
4. Select application type (`Web application`).
5. Name the application.
6. Add an Authorized redirect URI (`https://<host>:8088/oauth-authorized/google`).
7. Create and download your client ID and client secret.

### Apply OAuth configuration to OAuth2 Proxy charm

The oauth2-proxy-k8s charm manages all OAuth configuration for Airbyte. Create a file `oauth2-proxy.yaml` containing your Google OAuth details:

```yaml
oauth2-proxy-k8s:
  client_id: "<google_client_id>"
  client_secret: "<google_client_secret>"
  cookie_secret: "<random_32_byte_secret>"
  external_hostname: "airbyte.company.com"
  authenticated_emails_list: "user1@company.com,user2@company.com,<service-account>"
  additional_config: "--upstream-timeout=1200s --skip-jwt-bearer-tokens=true --extra-jwt-issuers=https://accounts.google.com=<google_client_id>"
  upstream: "http://airbyte-k8s:8001"
```

- `cookie_secret` must be a 32-byte base64-encoded value
- `external_hostname` must match what Google OAuth expects
- `authenticated_emails_list` controls who can access Airbyte

Apply the configuration:

```bash
juju config oauth2-proxy-k8s --file=path/to/oauth2-proxy.yaml
```

### Relate OAuth2 Proxy with Nginx Ingress Integrator

Finally, relate the OAuth2 Proxy with the Nginx Ingress Integrator to expose it through the ingress:

```bash
juju relate oauth2-proxy-k8s nginx-ingress-integrator
```

This will update the running `oauth2-proxy` unit and enforce Google OAuth in front of Airbyte.
