# Charmed Airbyte Architecture

The Charmed Airbyte deployment consists of multiple charms orchestrated to provide data ingestion, workflow scheduling, authentication, ingress, and object storage. This diagram reflects a high-level architecture.

## High-Level Architecture Diagram

```
                          ┌─────────────────────────┐
                          │         LEGO (ACME)      │
                          │   Optional TLS provider  │
                          └──────────┬───────────────┘
                                     │ certificates
                     ┌───────────────▼────────────────┐
                     │     Nginx Ingress Integrator    │
                     │ (for Airbyte UI + OAuth2 Proxy) │
                     └───────┬───────────────┬────────┘
                             │               │
                nginx-route  │               │ nginx-route
                             │               │
                     ┌───────▼───────────────▼───────────────┐
                     │           OAuth2 Proxy K8s             │
                     │  (AuthN/AuthZ + upstream to Airbyte)   │
                     └──────────┬─────────────────────────────┘
                                │ upstream
                     ┌──────────▼───────────┐
                     │     Airbyte-k8s      │
                     │  Server / Scheduler  │
                     │  API + Web UI        │
                     └──────────┬───────────┘
                                │
        ┌───────────────────────┼──────────────────────────┐
        │                       │                          │
┌───────▼────────┐     ┌────────▼──────────┐       ┌────────▼────────┐
│     MinIO      │     │ PostgreSQL (DBaaS)│       │    Temporal     │
│ Object Storage │     │ External via offer│       │   Orchestration │
└────────────────┘     └───────────────────┘       └────────┬────────┘
                                                             │ admin
                                                   ┌─────────▼─────────┐
                                                   │ Temporal Admin K8s │
                                                   └────────────────────┘


                      ┌────────────────────────────────────────┐
                      │      Airbyte Webhooks K8s              │
                      │ (Webhook → Temporal Workflow triggers) │
                      └──────────┬─────────────────────────────┘
                                 │ ingress
                ┌────────────────▼─────────────────────────────┐
                │  Nginx Ingress Integrator (Webhooks only)    │
                └──────────────────────────────────────────────┘
```

---

# Component Descriptions

### Airbyte-k8s
* Runs the server, scheduler and API.
* Uses MinIO as object storage.
* Uses an external PostgreSQL database (DBaaS) because cross-controller relations are disabled.
* Integrates with:
  * OAuth2 Proxy for authentication
  * MinIO for blobs, logs, state
  * Ingress via the first nginx ingress integrator

### OAuth2 Proxy
* Protects the Airbyte behind Google OAuth / GitHub OAuth / SSO.
* Acts as a reverse proxy for the Airbyte.
* Exposed through the same nginx ingress integrator as Airbyte.

### Nginx Ingress Integrator (Airbyte)
One instance for:
* Airbyte
* OAuth2 Proxy
* Certificates from Lego

This ingress handles:
* HTTP routing
* TLS termination (if Lego or a manual TLS secret is configured)
* Source-range whitelisting
* Timeout configuration

### Nginx Ingress Integrator (Webhooks)
A separate ingress dedicated to the Airbyte Webhooks application.

Its purpose is to:
* Keep webhook routing isolated
* Enable different hostname/paths
* Simplify independent TLS or routing behavior

### Lego
ACME provider for TLS certificates.

It is only used if one wants Let’s Encrypt certificates. Airbyte will still work without Lego (HTTP mode or user-supplied TLS secret).

### MinIO
Its purpose is to store state, large logs (objects) and job artifacts

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

### Airbyte Webhooks
A separate charm:
* Receives webhook events
* Authenticates + transforms payloads
* Triggers Temporal workflows
* Uses Temporal as downstream execution engine

Exposed through its own nginx ingress integrator.