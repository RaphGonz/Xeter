"""
S3/MinIO upload client for the Analyser service.

Provides:
  - S3Client: class with upload_span_payloads coroutine
  - get_s3_client: factory function reading credentials from environment

Key structure: {tenant_id}/{YYYY-MM}/{span_id}/{field}.json
Fields uploaded: prompt, response, raw_response, available_tools

If upload fails, the exception propagates to the caller.
The caller (ingest handler, Plan 03) must treat any exception as a 5xx condition.
Per the locked decision: ClickHouse never receives a row without its S3 payloads.

Environment variables:
  S3_ENDPOINT_URL  — MinIO URL, e.g. http://minio:9000
  S3_ACCESS_KEY    — MinIO access key
  S3_SECRET_KEY    — MinIO secret key
  S3_BUCKET        — bucket name, default "xeter-payloads"
"""

import json
import logging
import os
from datetime import datetime, timezone

import aioboto3

logger = logging.getLogger(__name__)


class S3Client:
    """Async S3/MinIO client for uploading span payload fields.

    Uses aioboto3 context manager pattern for each upload operation.
    Uploads are sequential (not parallel) to avoid connection issues
    with single-threaded MinIO in local development.
    """

    def __init__(
        self,
        session: aioboto3.Session,
        bucket: str,
        endpoint_url: str,
    ) -> None:
        """Initialise S3Client.

        Args:
            session:      aioboto3.Session pre-configured with credentials.
            bucket:       Target S3 bucket name.
            endpoint_url: MinIO/S3 endpoint URL, e.g. http://minio:9000.
        """
        self._session = session
        self._bucket = bucket
        self._endpoint_url = endpoint_url

    async def upload_span_payloads(
        self,
        tenant_id: str,
        span_id: str,
        prompt: str | None,
        response: str | None,
        raw_response: str | None,
        available_tools: str | None,
    ) -> dict[str, str]:
        """Upload four payload fields to S3.

        Each field is uploaded as a JSON object: {"value": <field_value>}.
        A None value is uploaded as {"value": null} — the S3 key always exists.

        Key structure: {tenant_id}/{YYYY-MM}/{span_id}/{field}.json
        Content-Type: application/json for all objects.

        Uploads are sequential to avoid connection issues with single-threaded
        MinIO in local development.

        Args:
            tenant_id:       Tenant UUID string (path segment).
            span_id:         Span UUID string (path segment).
            prompt:          Prompt text, or None.
            response:        Response text, or None.
            raw_response:    Raw LLM response text, or None.
            available_tools: Available tools JSON string, or None.

        Returns:
            dict with keys: prompt_ref, response_ref, raw_response_ref,
            available_tools_ref — each containing the S3 key string.

        Raises:
            Any exception from aioboto3 if an upload fails.
            Caller must treat this as a 5xx condition.
        """
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        prefix = f"{tenant_id}/{month}/{span_id}"
        refs: dict[str, str] = {}

        fields = [
            ("prompt", prompt),
            ("response", response),
            ("raw_response", raw_response),
            ("available_tools", available_tools),
        ]

        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
        ) as s3_client:
            for field_name, field_value in fields:
                key = f"{prefix}/{field_name}.json"
                body = json.dumps({"value": field_value}).encode("utf-8")
                await s3_client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=body,
                    ContentType="application/json",
                )
                refs[f"{field_name}_ref"] = key
                logger.debug("s3: uploaded %s", key)

        return refs


def get_s3_client() -> S3Client:
    """Create an S3Client from environment variables.

    Required environment variables:
      S3_ENDPOINT_URL — MinIO/S3 endpoint URL
      S3_ACCESS_KEY   — access key ID
      S3_SECRET_KEY   — secret access key

    Optional:
      S3_BUCKET       — bucket name (default: "xeter-payloads")

    Returns:
        A configured S3Client instance.

    Raises:
        KeyError: If a required environment variable is not set.
    """
    return S3Client(
        session=aioboto3.Session(
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        ),
        bucket=os.environ.get("S3_BUCKET", "xeter-payloads"),  # [safe-default] bucket name only, not a secret
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
    )
