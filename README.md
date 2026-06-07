# WPLokerBJM Post Automation

Telegram and CLI automation for converting job vacancy flyers into structured
WordPress `lowongan` drafts.

The service:

- Reads flyer images with Gemini.
- Loads current taxonomy options from WordPress before extraction.
- Applies the bundled `job-copywriter` and `agent-postdraft` skills.
- Normalizes fields to the WordPress ingest schema.
- Uploads the original flyer as the featured image.
- Runs as a Render Web Service with a Telegram webhook.

## Requirements

- Python 3.14
- [`uv`](https://docs.astral.sh/uv/)
- Google AI Studio API key
- WordPress with the WPLokerBJM GraphQL JWT mutation and REST ingest endpoints
- Telegram bot token from BotFather

## Environment

Copy `.env.example` to `.env` for local development. On Render, add the same
values under **Environment**.

```env
WPLBJM_API_BASE_URL_PROD=https://wp.example.com
WPLBJM_API_BASE_URL_DEV=https://localhost
WPLBJM_WORDPRESS_DOMAIN=https://wp.example.com

WPLBJM_JWT_DEV=
WPLBJM_JWT_PROD=

WP_LOGIN_USERNAME=
WP_LOGIN_PASSWORD=

AI_STUDIO_KEY=

TELEGRAM_USERNAME=allowed_username_without_at
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
PUBLIC_BASE_URL=

SKILL_MD_PATH=.agents/skills/agent-postdraft/SKILL.md
```

### Environment Notes

- `TELEGRAM_USERNAME` is the only Telegram username allowed to use the bot.
  It is read from env and cannot be changed through Telegram. Change it by
  updating the environment and redeploying.
- `TELEGRAM_WEBHOOK_SECRET` is compared with Telegram's
  `X-Telegram-Bot-Api-Secret-Token` header.
- `PUBLIC_BASE_URL` is optional. When empty, the service automatically uses
  Render's `RENDER_EXTERNAL_URL`, then `RENDER_EXTERNAL_HOSTNAME`.
- Set `PUBLIC_BASE_URL` only when Telegram should use a custom public domain.
- `WPLBJM_JWT_DEV` and `WPLBJM_JWT_PROD` are fallback tokens.
- `WP_LOGIN_USERNAME` and `WP_LOGIN_PASSWORD` are optional fallbacks for
  `/refresh_jwt` when credentials are not included in the command.
- `WPLBJM_WORDPRESS_DOMAIN` is used by the GraphQL JWT mutation.
- `GEMINI_API_KEY` may be used instead of `AI_STUDIO_KEY`.
- `GEMINI_MODEL` may override the default `gemini-2.5-flash`.

## Skill Loading

Skill instructions use this precedence:

1. A `SKILL.md` uploaded through Telegram.
2. The file configured by `SKILL_MD_PATH`.
3. Both bundled repository skills:
   - `.agents/skills/job-copywriter/SKILL.md`
   - `.agents/skills/agent-postdraft/SKILL.md`

`SKILL_MD_PATH` is a path, not Markdown content. Relative paths are resolved
from this repository directory.

A Telegram-uploaded skill is stored in process memory. It is cleared whenever
Render restarts or redeploys, after which the configured or bundled fallback is
used again.

## Local CLI

Install dependencies:

```bash
uv sync
```

Extract and preview a flyer without posting:

```bash
uv run python agent.py path/to/flyer.webp --target DEV
```

Create a WordPress draft:

```bash
uv run python agent.py path/to/flyer.webp --target DEV --post
uv run python agent.py path/to/flyer.webp --target PROD --post
```

`DEV` is the default target. Posting to WordPress only occurs when `--post` is
provided.

## Render Deployment

Create a Render **Web Service** from this repository.

Recommended settings:

```text
Runtime: Python
Build Command: python -m pip install uv==0.11.19 && python -m uv sync --frozen
Start Command: .venv/bin/python agent.py --serve
Health Check Path: /healthz
```

The server binds to `0.0.0.0` using Render's `PORT` environment variable.

The build command explicitly installs the same `uv` version used to create the
lockfile. Calling it as `python -m uv` bypasses Render's native `uv` wrapper,
which can occasionally exist without its underlying executable. The start
command runs the synchronized virtual environment directly and therefore does
not require `uv` at runtime.

After deployment, verify:

```bash
curl https://wplokerbjm-post-automation.onrender.com
```

Expected response:

```json
{
  "ok": true,
  "service": "wplokerbjm-post-automation",
  "public_url": "https://wplokerbjm-post-automation.onrender.com",
  "telegram_webhook_url": "https://wplokerbjm-post-automation.onrender.com/telegram/webhook"
}
```

## Telegram Setup

Create the bot through BotFather, then set `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_USERNAME`, and `TELEGRAM_WEBHOOK_SECRET` in Render.

On startup, the service automatically reads Render's built-in
`RENDER_EXTERNAL_URL` and registers:

```text
https://YOUR-SERVICE.onrender.com/telegram/webhook
```

The webhook is refreshed automatically after every restart or deployment.
No Render URL environment variable needs to be entered during onboarding.

Manual registration is only needed for troubleshooting:

```bash
curl -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://YOUR-SERVICE.onrender.com/telegram/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

Check registration:

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

## Telegram Commands

```text
/help
/status
/set_domain https://wp.example.com
/refresh_jwt <wordpress_username> <wordpress_password>
/set_jwt <wordpress_username> <wordpress_password>
/set_skill (caption on an attached SKILL.md document)
/reset_skill
```

### Set or Refresh JWT

`/refresh_jwt` sends this GraphQL mutation to `{WordPress domain}/graphql`:

```graphql
mutation GetJWT($username: String, $password: String, $token: String) {
  jwt(username: $username, password: $password, token: $token)
}
```

The GraphQL field returns `ok`, while the actual token is extracted from the
`Set-Cookie: jwt-token=...` response header. The refreshed token is stored in
process memory and overrides env JWT values until the service restarts.

Avoid sending credentials in Telegram when possible. Configure
`WP_LOGIN_USERNAME` and `WP_LOGIN_PASSWORD`, then send:

```text
/refresh_jwt
```

### Upload a Skill

Send a UTF-8 Markdown document with `/set_skill` as its caption:

```text
/set_skill
```

Maximum upload size is 256 KB. Use `/reset_skill` to discard the runtime upload
and restore the env/repository fallback.

### Process Flyers

- Send an image without a caption to extract and preview using `DEV`.
- Send an image with `/post_dev` as the caption to create a DEV draft.
- Send an image with `/post_prod` as the caption to create a PROD draft.
- Images may be sent as Telegram photos or image documents.

The bot returns the extracted title, company, gender, contacts, warnings, and
WordPress draft information when posting succeeds.

## WordPress Contract

Options:

```text
GET /wp-json/wplokerbjm/v1/lowongan/ingest/options
Authorization: Bearer <JWT>
```

Draft ingest:

```text
POST /wp-json/wplokerbjm/v1/lowongan/ingest
Authorization: Bearer <JWT>
Content-Type: multipart/form-data
```

Multipart fields:

```text
payload=<JSON string>
featured_image=<original flyer>
```

Automated payload rules include:

- Titles end with ` | AI posted draft`.
- Missing flyer gender defaults to both `Pria` and `Wanita`.
- The reserved `perusahaan` taxonomy is omitted.
- Taxonomy values are validated against backend options.
- `social_media` uses the Meta Box cloned fieldset array shape.
- `source` records the local temporary or CLI image path.

Duplicate flyer hashes return HTTP `409` instead of creating another draft.

## Runtime Persistence

The following Telegram settings are runtime-only:

- WordPress domain set by `/set_domain`
- JWT refreshed by `/refresh_jwt`
- Uploaded `SKILL.md`

They reset when Render restarts or redeploys. Their env and repository values
remain the fallback source of truth.

## Security

- Keep all JWTs, API keys, bot tokens, and WordPress passwords in Render secrets.
- Never commit `.env`.
- Use a long random `TELEGRAM_WEBHOOK_SECRET`.
- Telegram access is restricted by exact username from `TELEGRAM_USERNAME`.
- Changing the allowed username requires an env update and redeployment.
- The bot never includes JWT values in normal responses.
