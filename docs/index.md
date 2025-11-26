[![Charmhub Badge](https://charmhub.io/airbyte-k8s/badge.svg)](https://charmhub.io/airbyte-k8s)
[![Release Edge](https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml/badge.svg)](https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml)

**Charmed Airbyte K8s Operator** is an open-source, production-ready data integration platform operator for **Kubernetes**, based on [Airbyte](https://airbyte.io/).

Airbyte simplifies the process of **extracting and loading data** from various sources into a variety of sources such as **data warehouses, data lakes, or data meshes**, enabling continuous, scheduled data synchronization to ensure data freshness and reliability.

The Charmed Airbyte K8s Operator automates the **deployment, configuration, and lifecycle management** of the Airbyte server on Kubernetes using **Juju**. It wraps the official Airbyte server distribution and integrates with other charms to form a complete data ingestion pipeline within the Canonical data ecosystem.

It is intended for **data engineers and platform teams** who want to automate and scale Airbyte deployments while maintaining consistency and observability across environments.

### Features

- Automated deployment and scaling on Kubernetes
- Seamless integration with PostgreSQL, Temporal, and object storage via Juju relations
- Simple Airbyte UI access for connector configuration and monitoring
- Ingress and authentication integration via Nginx and OAuth2 Proxy charms
- Observability through Juju relation-based configuration

### In this documentation

| Section | Description |
| --- | --- |
| **Tutorial** | **Get started** - A hands-on guide to deploying and configuring Charmed Airbyte, including creating your first data connection |
| **How-to guides** | **Step-by-step guides** - Instructions for common operational tasks and advanced configurations |
| **Reference** | **Technical reference** - Comprehensive details on configuration options, actions, relations, and APIs |