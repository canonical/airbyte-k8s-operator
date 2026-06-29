# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""S3 helpers."""

import logging

import boto3
from botocore.exceptions import ClientError

from connections import ObjectStorageConnection, S3Connection

logger = logging.getLogger(__name__)


class S3Client:
    """Client for S3 operations."""

    def __init__(self, s3_parameters: ObjectStorageConnection | S3Connection):
        """Initialize an S3 connection using the provided parameters.

        Args:
            s3_parameters: object-storage or S3 connection details.

        Raises:
            ValueError: If a session fails to be created.
        """
        self.s3_parameters = s3_parameters
        region = getattr(s3_parameters, "region", None)  # Region can be optional for MinIO
        session = boto3.session.Session(
            aws_access_key_id=s3_parameters.access_key,
            aws_secret_access_key=s3_parameters.secret_key,
            region_name=region,
        )
        try:
            self.s3_resource = session.resource("s3", endpoint_url=s3_parameters.endpoint)
            self.s3_client = session.client("s3", endpoint_url=s3_parameters.endpoint)
        except Exception as e:
            logger.exception("Failed to create a session in region=%s.", region)
            raise ValueError("Failed to create a session") from e

    def create_bucket_if_not_exists(self, bucket_name):
        """Create the S3 bucket if it does not exist.

        Args:
            bucket_name (str): name of bucket to create

        Raises:
            e (ValueError): if a session could not be created.
            error (ClientError): if the bucket could not be created.
        """
        region = getattr(self.s3_parameters, "region", None)
        s3_bucket = self.s3_resource.Bucket(bucket_name)
        try:
            s3_bucket.meta.client.head_bucket(Bucket=bucket_name)
            logger.info("Bucket %s exists. Skipping creation.", bucket_name)
            exists = True
        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                logger.warning("Bucket %s doesn't exist or you don't have access to it.", bucket_name)
                exists = False
            else:
                logger.exception("Unexpected error: %s", e)
                raise

        if not exists:
            try:
                s3_bucket.create()
                s3_bucket.wait_until_exists()
                logger.info("Created bucket '%s' in region=%s", bucket_name, region)
            except ClientError as error:
                logger.exception("Couldn't create bucket named '%s' in region=%s.", bucket_name, region)
                raise error

    def set_bucket_lifecycle_policy(self, bucket_name, ttl):
        """Set lifecycle policy of bucket to purge files after a certain time.

        Args:
            bucket_name: Name of bucket.
            ttl: Time to live of logs (in days).
        """
        lifecycle_policy = {
            "Rules": [
                {
                    "Expiration": {"Days": ttl},
                    "Filter": {"Prefix": ""},
                    "Status": "Enabled",
                    "ID": "ttl",
                }
            ]
        }
        self.s3_client.put_bucket_lifecycle_configuration(Bucket=bucket_name, LifecycleConfiguration=lifecycle_policy)
