# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""S3 helpers."""

import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3Client:
    """Client for S3 operations."""

    def __init__(self, s3_parameters):
        """Initialize an S3 connection using the provided parameters.

        Args:
            s3_parameters: S3 connection parameters.

        Raises:
            ValueError: If a session fails to be created.
        """
        self.s3_parameters = s3_parameters
        endpoint = s3_parameters.get("endpoint")
        session = boto3.session.Session(
            aws_access_key_id=s3_parameters.get("access-key"),
            aws_secret_access_key=s3_parameters.get("secret-key"),
            region_name=s3_parameters.get("region"),  # Region can be optional for MinIO
        )
        try:
            self.s3_resource = session.resource("s3", endpoint_url=endpoint)
            self.s3_client = session.client("s3", endpoint_url=endpoint)
        except Exception as e:
            logger.exception("Failed to create a session in region=%s.", s3_parameters.get("region"))
            raise ValueError("Failed to create a session") from e

    def create_bucket_if_not_exists(self, bucket_name):
        """Create the S3 bucket if it does not exist.

        Args:
            bucket_name (str): name of bucket to create

        Raises:
            e (ValueError): if a session could not be created.
            error (ClientError): if the bucket could not be created.
        """
        region = self.s3_parameters.get("region")
        s3_bucket = self.s3_resource.Bucket(bucket_name)
        try:
            s3_bucket.meta.client.head_bucket(Bucket=bucket_name)
            logger.info("Bucket %s exists.", bucket_name)
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
