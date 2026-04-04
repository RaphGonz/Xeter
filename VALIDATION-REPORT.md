# Validation Report

Generated: 2026-04-04 18:33:20 UTC
Overall result: **PASS**

## E2E Smoke Test

| Step | Status | Duration |
|------|--------|----------|
| Register tenant | PASS | 674ms |
| Login | PASS | 301ms |
| Ingest span | PASS | 26780ms |
| Worker processing | PASS | 8365ms |
| Span detail + S3 | PASS | 552ms |

**Total E2E: 36671ms**

## Verification

- Span appears in list: YES
- Scores present: YES (5 metrics)
- S3 payloads returned: YES (prompt, response)
- Status: flagged
- Flags: 3
