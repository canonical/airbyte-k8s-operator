# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Typed data structures for relation-derived connection details."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConnection:
    """PostgreSQL connection details derived from the `db` relation.

    Attrs:
        dbname: the database name.
        host: the database host.
        port: the database port.
        user: the database username, if provided.
        password: the database password, if provided.
    """

    dbname: str
    host: str
    port: str
    user: str | None
    password: str | None


@dataclass(frozen=True)
class ObjectStorageConnection:
    """MinIO/object-storage details derived from the `object-storage` relation.

    Attrs:
        service: the object-storage service name.
        namespace: the namespace the service runs in.
        port: the object-storage port.
        secure: whether the endpoint uses TLS.
        access_key: the object-storage access key.
        secret_key: the object-storage secret key.
        endpoint: the constructed service endpoint URL.
    """

    service: str
    namespace: str
    port: str
    secure: bool
    access_key: str
    secret_key: str
    endpoint: str


@dataclass(frozen=True)
class S3Connection:
    """S3 details derived from the `s3-parameters` relation.

    Attrs:
        bucket: the S3 bucket name, if provided.
        endpoint: the S3 endpoint, if provided.
        region: the S3 region, if provided.
        access_key: the S3 access key, if provided.
        secret_key: the S3 secret key, if provided.
        uri_style: the S3 URI style, if provided.
    """

    bucket: str | None
    endpoint: str | None
    region: str | None
    access_key: str | None
    secret_key: str | None
    uri_style: str | None


@dataclass(frozen=True)
class ReconcileData:
    """Live-derived state assembled by `_validate` and consumed by `reconcile`.

    Attrs:
        db: the database connection details.
        minio: the object-storage details, or None when not configured.
        s3: the S3 details, or None when not configured.
        credentials: credentials resolved from Juju secrets (empty if none).
    """

    db: DatabaseConnection
    minio: ObjectStorageConnection | None
    s3: S3Connection | None
    credentials: dict[str, str]
