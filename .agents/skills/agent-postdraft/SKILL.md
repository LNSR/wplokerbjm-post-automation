---
name: agent-postdraft
description: >-
  Mengirim hasil ekstraksi lowongan WPLokerBJM ke WordPress sebagai draft dari
  flyer/image lokal. Gunakan skill ini saat agent perlu membaca flyer lowongan
  secara langsung dengan Vision, mengambil opsi taxonomy dari REST, memakai
  job-copywriter untuk payload, lalu POST multipart ke endpoint lowongan ingest
  dengan JWT dari env. Cocok untuk membuat draft review, mengunggah
  featured_image, menangani duplicate flyer, dan melaporkan edit URL tanpa
  membocorkan token.
---

# Agent Postdraft WPLokerBJM

## Goal

Buat draft `lowongan` di WordPress dari flyer lokal secara aman:

- Baca flyer secara langsung dengan kemampuan Vision agent.
- Ambil opsi taxonomy/status dari backend.
- Gunakan `job-copywriter` untuk membuat payload schema-first.
- Kirim `payload` + `featured_image` ke REST ingest endpoint.
- Laporkan hasil draft, warning, dan field yang tidak yakin.

Skill ini **tidak menggantikan** `job-copywriter`. Gunakan `job-copywriter`
untuk ekstraksi dan copywriting; gunakan skill ini untuk validasi posting,
env, REST, dan upload file.

## Required Inputs

- Satu atau lebih path gambar flyer lokal.
- Target environment:
  - Default: `DEV`.
  - `PROD` hanya jika user eksplisit meminta production.

Env yang digunakan:

```text
WPLBJM_API_BASE_URL_DEV
WPLBJM_API_BASE_URL_PROD
WPLBJM_JWT_DEV
WPLBJM_JWT_PROD
```

Token JWT tidak boleh ditulis ke prompt, payload, file output, log ringkasan,
atau final answer.

## Endpoints

Options:

```http
GET /wp-json/wplokerbjm/v1/lowongan/ingest/options
Authorization: Bearer <JWT>
```

Draft ingest:

```http
POST /wp-json/wplokerbjm/v1/lowongan/ingest
Authorization: Bearer <JWT>
Content-Type: multipart/form-data
```

Multipart fields:

```text
payload=<JSON string>
featured_image=<original flyer file>
```

Expected success response:

```json
{
  "id": 123,
  "status": "draft",
  "edit_url": "...",
  "permalink": "...",
  "warnings": []
}
```

## Workflow

1. Resolve env without printing secrets.
   - For DEV use `WPLBJM_API_BASE_URL_DEV` and `WPLBJM_JWT_DEV`.
   - For PROD use `WPLBJM_API_BASE_URL_PROD` and `WPLBJM_JWT_PROD`.
   - Do not shell-source `.env` directly if values may contain special chars.
     Parse key/value lines safely or use a language runtime.

2. Query ingest options before writing the payload.
   - Use the options endpoint with Bearer JWT.
   - Pass allowed taxonomy/status options into the extraction context.
   - Treat `reserved_taxonomies` as write-protected.

3. Read the flyer directly with Vision.
   - If the agent has Vision capability, inspect the image itself. Do not rely
     on OCR, filenames, captions, or inferred context as the primary source.
   - Use OCR only as a helper for tiny text, then verify the extracted facts
     against the image.
   - Extract only facts visible in the image or explicitly provided by user.
   - If multiple images are provided, process each image independently unless
     the user says they are one carousel/job.

4. Use `job-copywriter`.
   - Follow its field contract and QA checklist.
   - Do not output `ringkasanPekerjaan`.
   - Keep typed fields raw: integers and `YYYY-MM-DD`.
   - Keep WYSIWYG simple safe HTML.

5. Adjust for automated posting rules.
   - Omit `perusahaan` from payload unless useful as review context; backend
     will not assign it and may return a warning.
   - Append ` | AI posted draft` to the payload `title` before POST unless the
     title already ends with that suffix.
   - If the flyer does not mention gender, set `gender` to `Pria/Wanita` so the
     backend assigns both gender taxonomy terms. If the flyer explicitly limits
     gender, use only the visible requirement.
   - Convert cloned Meta Box fields to their stored array shapes before POST.
   - Always include `source` with the local image path when available.
   - Include at least one meaningful detail/contact field beyond title/company.

6. Summarize before POST.
   - Title.
   - Company.
   - Contacts.
   - Taxonomy choices.
   - Uncertain or omitted fields.
   - Target endpoint/environment.
   - Never include JWT.

7. POST multipart.
   - Write payload JSON to a temp file.
   - Send original image as `featured_image`.
   - Preserve the original file type.

8. Parse response defensively.
   - Prefer strict JSON, but if local WordPress appends PHP warnings/notices,
     recover the first JSON object from the response.
   - `201`: report draft ID, edit URL, permalink, warnings.
   - `409`: report duplicate flyer and existing ID if provided.
   - `400/401/403/500`: report status, code, message, and safe next step.

## Payload Rules For Posting

Accepted fields are the `job-copywriter` output fields plus:

```text
source
```

Important posting constraints:

- `title` is required.
- `featured_image` is required.
- `status_pekerjaan` defaults to `0` unless source/user clearly says urgent or pinned.
- `title` must include the suffix ` | AI posted draft` for every automated
  draft. Keep the human-readable job/company title before the suffix.
- `gender` defaults to `Pria/Wanita` when gender is not shown on the flyer; this
  intentionally checks both gender taxonomy terms for universal roles.
- `perusahaan` taxonomy is reserved for manual review and must not be treated as assigned.
- Unknown controlled taxonomy terms should be omitted or expected as backend warnings.

Meta Box clone fields:

- `email_kontak`, `nomor_kontak`, and `situs_kontak` are cloned scalar fields.
  Send them as comma-separated strings or arrays of scalar values.
- `social_media` is a cloned `fieldset_text`; send it as an array of platform
  objects, not as display text:

```json
{
  "social_media": [
    {
      "WhatsApp": "+6287844665424",
      "Instagram": "loker_banjarmasin"
    }
  ]
}
```

Allowed `social_media` keys:

```text
WhatsApp, Instagram, Facebook, X / Twitter, Threads, TikTok, LinkedIn, Youtube, Telegram
```

The frontend later renders this as `WhatsApp: ...; Instagram: ...`, but the
POST payload should use the cloned fieldset array shape.

Controlled taxonomies come from the options endpoint:

```text
kategori_lowongan
lokasi_pekerjaan
jenis_pekerjaan
gender
pendidikan
```

## Safe Local Curl Pattern

Use a temp payload file and avoid echoing token:

```bash
base="<resolved base url>"
token="<resolved jwt>"
image="/absolute/path/to/flyer.webp"

curl -sS -k \
  -X POST "$base/wp-json/wplokerbjm/v1/lowongan/ingest" \
  -H "Authorization: Bearer $token" \
  -F "payload=< /tmp/wplbjm-ingest-payload.json" \
  -F "featured_image=@${image};type=image/webp"
```

For non-WebP files, set the MIME type to the actual file type.

## Final Report

After posting, report:

- HTTP status.
- Draft ID.
- Edit URL.
- Permalink.
- Backend warnings.
- Any fields intentionally omitted.

Do not report:

- JWT value.
- Full env file contents.
- Raw response if it contains server paths, notices, or secrets.

## Failure Handling

- Missing env: say which key is missing, not its value.
- Options endpoint unavailable: do not invent taxonomy terms; proceed only with
  non-taxonomy fields or ask whether to continue.
- Duplicate `409`: do not repost the same image unless user explicitly asks
  for a duplicate.
- Production target: require explicit user intent before posting.
- if JWT is invalid or expired, report auth failure without echoing the token.
