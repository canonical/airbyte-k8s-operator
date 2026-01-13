# Charmed Airbyte Architecture

The Charmed Airbyte ecosystem consists of a number of different charmed operators related together. The diagram below shows a high-level illustration of the different charms and their communication.

![Architecture diagram](../media/architecture.png)

## Component Descriptions

### Airbyte-k8s

* Runs the server, scheduler and API.
* Uses MinIO as object storage.
* Uses a PostgreSQL database (DBaaS).
* Integrates with:
  * OAuth2 Proxy for authentication
  * MinIO for blobs, logs, state
  * Ingress via the first nginx ingress integrator

### OAuth2 Proxy

* Protects the Airbyte behind Google OAuth / GitHub OAuth / SSO.
* Acts as a reverse proxy for the Airbyte.
* Exposed through the same nginx ingress integrator as Airbyte.

### Nginx Ingress Integrator

One instance for:

* Airbyte
* OAuth2 Proxy

This ingress handles:

* HTTP routing
* TLS termination (if TLS secret is configured)
* Source-range allowlist
* Timeout configuration

### MinIO

Its purpose is to store state, large logs (objects) and job artifacts.

### Temporal-k8s

Orchestration engine powering:

* Job execution
* Retries
* Scheduling
* Long-running sync pipelines

### Temporal Admin

Provides:

* Namespace administration
* Workflow debugging tools
