Charmed Airbyte K8s Operator
============================

.. raw:: html

   <p>
   <a href="https://charmhub.io/airbyte-k8s"><img src="https://charmhub.io/airbyte-k8s/badge.svg" alt="Charmhub Badge"></a>
   <a href="https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml"><img src="https://github.com/canonical/airbyte-k8s-operator/actions/workflows/publish_charm.yaml/badge.svg" alt="Release Edge"></a>
   </p>

**Charmed Airbyte K8s Operator** is an open-source, production-ready data integration platform operator for **Kubernetes**, based on `Airbyte <https://airbyte.io/>`_.

Airbyte simplifies the process of **extracting and loading data** from various sources into a variety of destinations such as **data warehouses, data lakes, or data meshes**, enabling continuous, scheduled data synchronization to ensure data freshness and reliability.

The Charmed Airbyte K8s Operator automates the **deployment, configuration, and lifecycle management** of the Airbyte server on Kubernetes using **Juju**. It wraps the official Airbyte server distribution and integrates with other charms to form a complete data ingestion pipeline within the Canonical data ecosystem.

It is intended for **data engineers and platform teams** who want to automate and scale Airbyte deployments while maintaining consistency and observability across environments.

Features
--------

- Automated deployment and scaling on Kubernetes
- Seamless integration with PostgreSQL, Temporal, and object storage via Juju relations
- Simple Airbyte UI access for connector configuration and monitoring
- Ingress and authentication integration via Nginx and OAuth2 Proxy charms
- Observability through Juju relation-based configuration

.. toctree::
   :hidden:
   :maxdepth: 2

   Tutorials </tutorial/index>
   How-to guides </how-to/index>
   Reference </reference/index>

In this documentation
---------------------

.. grid:: 1 1 2 2

   .. grid-item-card:: Tutorial
      :link: /tutorial/index
      :link-type: doc

      **Get started** - A hands-on guide to deploying and configuring Charmed Airbyte, including creating your first data connection

   .. grid-item-card:: How-to guides
      :link: /how-to/index
      :link-type: doc

      **Step-by-step guides** - Instructions for common operational tasks and advanced configurations

.. grid:: 1 1 2 2

   .. grid-item-card:: Reference
      :link: /reference/index
      :link-type: doc

      **Technical reference** - Architecture, configuration options, actions, relations, and APIs
