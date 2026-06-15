<!-- Context: project-intelligence/lookup | Priority: critical | Version: 1.0 | Updated: 2026-06-15 -->

# Lookup: API Contracts

**Purpose**: Quick reference for REST and GraphQL endpoints used by the automation pipeline.

**Last Updated**: 2026-06-15

---

## REST Endpoints

| Endpoint | Method | Auth | Purpose | Source |
|----------|--------|------|---------|--------|
| `/wp-json/wplokerbjm/v1/lowongan/ingest` | POST | Bearer JWT | Post draft + featured_image | `ingest.py:post_draft()` |
| `/wp-json/wplokerbjm/v1/lowongan/ingest/options` | GET | Bearer JWT | Get taxonomy terms | `ingest.py:ingest_options()` |

---

## GraphQL Endpoint

| Endpoint | Method | Purpose | Source |
|----------|--------|---------|--------|
| `/graphql` | POST | JWT auth mutation | `auth.py:request_graphql_jwt()` |

**Mutation**:
```graphql
mutation GetJWT($username: String, $password: String, $token: String) {
  jwt(username: $username, password: $password, token: $token)
}
```

**Auth**: Uses `WP_LOGIN_USERNAME` + `WP_LOGIN_PASSWORD` from `.env`. JWT returned via `Set-Cookie: jwt-token=<token>`.

---

## Multipart Upload Format

```
------wplbjm{uuid}
Content-Disposition: form-data; name="payload"
{JSON payload}
------wplbjm{uuid}
Content-Disposition: form-data; name="featured_image"; filename="{image}"
Content-Type: image/jpeg
{binary image}
------wplbjm{uuid}--
```

Source: `automation/wordpress/ingest.py:encode_multipart()`

---

## Env Vars

| Variable | Purpose |
|----------|---------|
| `WPLBJM_API_BASE_URL_PROD` | WordPress base URL |
| `WPLBJM_JWT_PROD` | Active JWT token |
| `WP_LOGIN_USERNAME` | GraphQL auth username |
| `WP_LOGIN_PASSWORD` | GraphQL auth password |

---

## Commands

```bash
# Get options
curl -H "Authorization: Bearer $JWT" \
  "https://example.com/wp-json/wplokerbjm/v1/lowongan/ingest/options"

# Post draft
curl -X POST -H "Authorization: Bearer $JWT" \
  -F "payload=@payload.json" -F "featured_image=@flyer.jpg" \
  "https://example.com/wp-json/wplokerbjm/v1/lowongan/ingest"
```

---

## 📂 Codebase References

**Client**: `automation/wordpress/client.py:request_json()`, `parse_json_response()`
**Auth**: `automation/wordpress/auth.py:wordpress_config()`, `request_graphql_jwt()`, `jwt_from_headers()`
**Ingest**: `automation/wordpress/ingest.py:encode_multipart()`, `post_draft()`, `ingest_options()`

---

## Related

- `concepts/wordpress-schema.md` — Payload JSON structure
- `examples/payload-example.md` — Example payload
- `errors/common-errors.md` — JWT & draft errors
