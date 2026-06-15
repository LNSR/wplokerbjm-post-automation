<!-- Context: project-intelligence/guides | Priority: critical | Version: 1.0 | Updated: 2026-06-15 -->

# Guide: Automation Workflows

**Purpose**: End-to-end pipeline from flyer upload → AI extraction → normalisation → WordPress draft.

**Last Updated**: 2026-06-15

---

## Prerequisites

- Python 3.12+, `uv` environment active
- `.env` with valid credentials (JWT, WP URL, AI keys)
- `automation/` installed (`uv sync`)

**Estimated time**: 5-10 min per flyer

---

## Steps

### 1. Mock Preview (Dry Run)

```bash
python -m automation.main path/to/flyer.jpg
```

AI extracts → normalizes → prints JSON. Does NOT post.

**Expected**: `mode: "mock_preview"`, full `payload`, optional `warnings`.

---

### 2. Post Draft to WordPress

```bash
python -m automation.main path/to/flyer.jpg --post-prod
```

Full pipeline: extract → normalize → multipart POST → returns edit URL.

**Expected**: `mode: "post_prod"`, `http_status: 200`, `wordpress.edit_url`.

---

### 3. Telegram Bot (Webhook Mode)

```bash
python -m automation.main --serve
```

**Flow**: User sends flyer → bot downloads (`telegram/files.py`) → QR decode (`ai/qr.py`) → Gemini OCR (`ai/extractor.py`) → normalize (`payload/normalize.py`) → confirm via `/post_prod` → post via `wordpress/ingest.py:post_draft()` → return edit URL.

---

### 4. Validate Config

```bash
python -m automation.main --check-config
# Verify env vars without posting
```

### 5. Probe AI Models

```bash
python -m automation.main --probe-opencode
# Test all models in chain for API access
```

---

## Verification

```bash
python -m automation.main path/to/flyer.jpg | python -m json.tool
# Check for: "payload" with valid fields, empty "warnings"
```

---

## 📂 Codebase References

**Entry**: `automation/main.py` — CLI + orchestrator
**AI**: `automation/ai/extractor.py:extract_payload_from_image()`, `ai/gemini.py`, `ai/qr.py`, `ai/prompt.py`
**Payload**: `automation/payload/normalize.py:normalize_payload()`, `payload/constants.py`
**WordPress**: `automation/wordpress/ingest.py:post_draft()`, `wordpress/auth.py:wordpress_config()`, `wordpress/client.py`
**Telegram**: `automation/telegram/server.py:serve_bot()`, `handlers.py`, `files.py`, `state.py`

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Model chain fails | Check `OPENCODE_API_KEY` / `GOOGLE_AI_STUDIO_KEY` |
| WP returns 401 | Refresh JWT via `/refresh_jwt` |
| Image too large | Resize to <10MB |

---

## Related

- `concepts/wordpress-schema.md` — Data model
- `lookup/api-contracts.md` — Endpoints
- `examples/payload-example.md` — Payload shape
- `errors/common-errors.md` — Known failures
