# Xeter Deployment Guide

## MinIO / S3 Bucket Privacy

The `xeter-payloads` bucket must be private (no anonymous read/write). Xeter enforces
this automatically in the local Docker stack via `minio-init`, and operators must
enforce it manually when deploying to cloud S3.

### Local Docker Stack (MinIO)

The `minio-init` container runs the following on every `docker compose up`:

```bash
mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}
mc mb local/xeter-payloads --ignore-existing
mc anonymous set none local/xeter-payloads
```

`mc anonymous set none` removes all anonymous access policies from the bucket.
This is the current command (post-mc RELEASE.2021). The older `mc policy set none`
is deprecated — do not use it.

### Cloud Deployment (AWS S3)

When using AWS S3 instead of MinIO, block all public access at the bucket level:

```bash
aws s3api put-public-access-block \
  --bucket xeter-payloads \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

Verify the setting was applied:

```bash
aws s3api get-public-access-block --bucket xeter-payloads
```

Expected output: all four flags set to `true`.

### Why This Matters

An anonymous-accessible bucket would expose all ingested payloads to the public
internet. The `xeter-payloads` bucket stores raw diagnostic data — it must never
be publicly readable or writable.
