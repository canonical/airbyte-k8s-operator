Deploy Supporting Charms
=========================

This part of the tutorial focuses on deploying supporting charms that Airbyte requires for metadata storage, workflow orchestration, and object storage.

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Requirement
     - Charm
     - Purpose
   * - **Database**
     - `postgresql-k8s <https://charmhub.io/postgresql-k8s>`_
     - Stores metadata, job configurations, and sync history
   * - **Workflow Engine**
     - `temporal-k8s <https://charmhub.io/temporal-k8s>`_
     - Manages task queues and workflow execution
   * - **Admin UI**
     - `temporal-admin-k8s <https://charmhub.io/temporal-admin-k8s>`_
     - Manages Temporal namespaces and admin tasks
   * - **Object Storage**
     - `minio <https://charmhub.io/minio>`_ or `S3 Integrator <https://charmhub.io/s3-integrator>`_
     - Stores sync logs, state, and artifacts
   * - **Ingress**
     - `nginx-ingress-integrator <https://charmhub.io/nginx-ingress-integrator>`_
     - Provides TLS termination and routing

.. note::
   Either MinIO or S3 Integrator can be used; not both.

Deploy PostgreSQL
-----------------

.. code-block:: bash

   juju deploy postgresql-k8s --channel 14/edge --trust
   juju status --watch 2s

.. note::
   Deployment may take ~10 minutes. Expect ``active`` status for all units once complete.

Deploy MinIO
------------

.. code-block:: bash

   juju deploy minio --channel edge
   juju status --watch 2s

.. note::
   Deployment completes when all units are ``active``.

Deploy Temporal
---------------

.. code-block:: bash

   juju deploy temporal-k8s --config num-history-shards=4  # This value can be set to 1024 or 2048 for a production deployment
   juju deploy temporal-admin-k8s
   juju status --watch 2s

.. note::
   Temporal requires ``num-history-shards`` to be a power of 2.

Ignore temporary ``blocked`` messages; they will be resolved once relations are added in the next step.

Deploy Nginx Ingress Integrator
--------------------------------

.. code-block:: bash

   juju deploy nginx-ingress-integrator --trust
   juju status --watch 2s

----

**See next:** :doc:`Deploy Charmed Airbyte <04-deploy-airbyte>`
