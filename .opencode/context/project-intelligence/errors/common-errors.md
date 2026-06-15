<!-- Context: project-intelligence/errors | Priority: high | Version: 1.0 | Updated: 2026-06-15 -->

# Errors: Common Automation Errors

**Purpose**: Known errors from the automation pipeline — JWT, options, draft post, and validation failures.

**Last Updated**: 2026-06-15

---

## Error: JWT Refresh Failed

**Symptom**:
```
JWT refresh failed (401): ...
JWT refresh failed: GraphQL did not set jwt-token cookie.
```

**Cause**: `WP_LOGIN_USERNAME`/`WP_LOGIN_PASSWORD` incorrect, `/graphql` unreachable, or JWT plugin inactive.

**Solution**:
1. Verify credentials in `.env`
2. Check `WPLBJM_API_BASE_URL_PROD` is correct
3. Test `/graphql` responds 200
4. Run `/refresh_jwt` in Telegram bot

**Code**: `automation/wordpress/auth.py:request_graphql_jwt()`

**Frequency**: occasional

---

## Error: Options Request Failed

**Symptom**:
```
Options request failed (404 options_request_failed)
```

**Cause**: `/wp-json/wplokerbjm/v1/lowongan/ingest/options` not found — plugin not installed/active.

**Solution**: Verify `wplokerbjm` WP plugin is installed and active. Check `base_url` config.

**Code**: `automation/wordpress/ingest.py:ingest_options()`

**Frequency**: common

---

## Error: Draft Post Failed

**Symptom**:
```
Draft post failed: <reason>
Draft post failed (4xx): ...
```

**Cause**: JWT expired, image >10MB, WP validation error, or network timeout.

**Solution**:
1. Refresh JWT via `/refresh_jwt`
2. Check image file size
3. Validate payload against `NormalizedPayload`
4. Check WP server logs
5. Always dry-run first: `python -m automation.main image.jpg`

**Code**: `automation/wordpress/ingest.py:post_draft()`

**Frequency**: occasional

---

## Error: Response Not Valid JSON

**Symptom**:
```
Response was not valid JSON.
```

**Cause**: PHP notices prepended before JSON response (common in local WP dev).

**Solution**: `parse_json_response()` auto-recovers by extracting first `{...}` block. If still failing, disable `WP_DEBUG_DISPLAY`.

```python
start = body.find("{"); end = body.rfind("}")
if start >= 0 and end > start:
    return json.loads(body[start : end + 1])
```

**Code**: `automation/wordpress/client.py:parse_json_response()`

**Frequency**: common (local dev), rare (production)

---

## Error: Title Missing

**Symptom**:
```
Extracted payload is missing title.
```

**Cause**: AI could not extract title — flyer blurry, non-standard, or not a job posting.

**Solution**: Use clearer image. Try different AI model via `--model` flag.

**Code**: `automation/payload/normalize.py:normalize_payload()` line 281-282

**Frequency**: occasional

---

## Error: Payload Validation Failed

**Symptom**:
```
Normalized payload failed strict validation: field: error
```

**Cause**: Type mismatch (string in INT field), unexpected field, or invalid value.

**Solution**: Check the specific field in error. Verify AI data types. Review `warnings` array.

**Code**: `automation/models.py:NormalizedPayload`, `normalize.py:normalize_payload()`

**Frequency**: rare

---

## 📂 Codebase References

**Errors**: `automation/models.py:AgentError`, `validation_error_summary()`
**Handlers**: `automation/wordpress/client.py:parse_json_response()`, `main.py:main()`
**Prevention**: `automation/payload/normalize.py:normalize_payload()`, `constants.py:ACCEPTED_PAYLOAD_FIELDS`

---

## Related

- `concepts/wordpress-schema.md` — Data model
- `guides/automation-workflows.md` — Dry-run first workflow
- `lookup/api-contracts.md` — Endpoint verification
