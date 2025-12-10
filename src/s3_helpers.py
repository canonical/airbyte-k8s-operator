# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""S3 helpers."""

import logging

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

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
        region = s3_parameters.get("region")
        # Persist commonly used fields for later methods
        self.endpoint = endpoint
        self.region = region
        session = boto3.session.Session(
            aws_access_key_id=s3_parameters.get("access-key"),
            aws_secret_access_key=s3_parameters.get("secret-key"),
            region_name=region,  # Region can be optional for MinIO
        )

        # Determine addressing style: AWS prefers virtual-hosted; MinIO often needs path-style
        uri_style = (s3_parameters.get("uri_style") or "").lower()
        if uri_style in {"host", "virtual"}:
            addressing_style = "virtual"
        elif uri_style in {"path", "path-style"}:
            addressing_style = "path"
        else:
            # Fallback based on endpoint
            if endpoint and "amazonaws.com" in endpoint:
                addressing_style = "virtual"
            else:
                addressing_style = "path"

        cfg = Config(
            s3={"addressing_style": addressing_style},
            signature_version="s3v4",
            retries={"max_attempts": 10, "mode": "standard"},
        )
        try:
            self.s3_resource = session.resource("s3", endpoint_url=endpoint, config=cfg)
            self.s3_client = session.client("s3", endpoint_url=endpoint, config=cfg)
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
        region = self.region
        s3_bucket = self.s3_resource.Bucket(bucket_name)
        try:
            s3_bucket.meta.client.head_bucket(Bucket=bucket_name)
            logger.info("Bucket %s exists. Skipping creation.", bucket_name)
            exists = True
        except ClientError as e:
            error_code = str(e.response.get("Error", {}).get("Code", ""))
            # AWS may return 301/PermanentRedirect when the endpoint or region doesn't match.
            if error_code in {"404", "NoSuchBucket"}:
                logger.warning("Bucket %s doesn't exist or you don't have access to it.", bucket_name)
                exists = False
            elif error_code in {"301", "PermanentRedirect"}:
                logger.warning(
                    "Received redirect when checking bucket %s (code=%s). Verify endpoint/region; treating as existing.",
                    bucket_name,
                    error_code,
                )
                exists = True
            else:
                logger.exception("Unexpected error when checking bucket '%s': %s", bucket_name, e)
                raise

        if not exists:
            try:
                # For AWS, creating a bucket requires LocationConstraint when region != us-east-1
                if self.endpoint and "amazonaws.com" in self.endpoint and region and region != "us-east-1":
                    s3_bucket.create(CreateBucketConfiguration={"LocationConstraint": region})
                else:
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
