from __future__ import annotations

import json
from typing import Any

from automation.payload.constants import (
    ACCEPTED_PAYLOAD_FIELDS,
    CONTROLLED_TAXONOMIES,
    INT_FIELDS,
    SOCIAL_MEDIA_KEYS,
    TITLE_SUFFIX,
)
from automation.skills import load_skill_markdown


def extraction_schema() -> dict[str, Any]:
    string_fields = [
        "title",
        "nama_perusahaan",
        "perusahaan",
        "kategori_lowongan",
        "lokasi_pekerjaan",
        "jenis_pekerjaan",
        "gender",
        "pendidikan",
        "deadline",
        "tentang_perusahaan",
        "deskripsi_pekerjaan",
        "persyaratan",
        "cara_melamar",
        "benefit",
        "email_kontak",
        "nomor_kontak",
        "situs_kontak",
    ]
    properties: dict[str, Any] = {
        field: {"type": "STRING", "nullable": True} for field in string_fields
    }
    properties.update({field: {"type": "INTEGER", "nullable": True} for field in INT_FIELDS})
    properties["social_media"] = {
        "type": "ARRAY",
        "nullable": True,
        "items": {
            "type": "OBJECT",
            "properties": {key: {"type": "STRING", "nullable": True} for key in SOCIAL_MEDIA_KEYS},
        },
    }
    properties["uncertain_fields"] = {
        "type": "ARRAY",
        "nullable": True,
        "items": {"type": "STRING"},
    }
    return {"type": "OBJECT", "properties": properties}


def build_prompt(
    options: dict[str, Any],
    custom_instruction: str | None = None,
) -> str:
    taxonomies = options.get("taxonomies") if isinstance(options.get("taxonomies"), dict) else {}
    allowed = {
        name: [term.get("name") for term in terms if isinstance(term, dict) and term.get("name")]
        for name, terms in taxonomies.items()
        if name in CONTROLLED_TAXONOMIES and isinstance(terms, list)
    }
    skill_markdown, _ = load_skill_markdown()
    accepted_fields = sorted(ACCEPTED_PAYLOAD_FIELDS - {"perusahaan"})

    operator_instruction = ""
    if custom_instruction:
        operator_instruction = f"""

Optional instruction for this flyer:
<operator_instruction>
{json.dumps(custom_instruction, ensure_ascii=False)}
</operator_instruction>
Follow this instruction only when it is compatible with the strict JSON contract,
visible flyer evidence, taxonomy restrictions, and safety rules above.
It must never add unsupported fields or invented facts.
"""

    return f"""
You are extracting one Indonesian job vacancy flyer for WPLokerBJM.

Return only one JSON object. Do not wrap it in markdown.

Follow these operator-provided skill instructions:
<skill>
{skill_markdown}
</skill>

STRICT JSON CONTRACT:
- The response object may use only these keys:
{json.dumps(accepted_fields + ["uncertain_fields"], ensure_ascii=False)}
- Do not output camelCase keys.
- Do not output Indonesian synonym keys such as kualifikasi, deskripsi, kontak, gaji, alamat, lokasi_kerja, berkas_lamaran, or info_lainnya.
- Map flyer facts into the exact contract keys:
  - qualifications/requirements/documents/skills -> persyaratan
  - duties/work scope -> deskripsi_pekerjaan
  - application method/address/contact instructions -> cara_melamar
  - salary/allowance/facility -> benefit, or gaji_minimal/gaji_maksimal only when numeric salary is explicit
  - phone/WhatsApp -> nomor_kontak
  - email -> email_kontak
  - website/link -> situs_kontak
- If a fact does not fit an allowed key, omit it or mention the field name in uncertain_fields.

Rules:
- Extract only facts visible in the flyer. Do not invent company profiles, salary, location, deadline, or contacts.
- If decoded QR code content is provided with the image, treat it as visible
  flyer evidence. Use QR URLs for situs_kontak or cara_melamar only when they
  are clearly application/contact links.
- If web search context is provided, use it only to validate or enrich contact
  URLs, public address/map clues, or company identity already suggested by the
  flyer/QR. Do not invent salary, requirements, deadline, or job facts from web
  search alone.
- Do not include ringkasanPekerjaan.
- title must be short and searchable. Use "Posisi | Perusahaan" when company is visible.
- Append "{TITLE_SUFFIX}" to title.
- If gender is visible, use only the visible requirement: "Pria", "Wanita", or "Pria/Wanita".
- If gender is not visible, set gender to "Pria/Wanita".
- status_pekerjaan must be 0 unless the flyer explicitly says urgent or pinned.
- Omit perusahaan unless explicitly needed as review context. It is reserved by the backend.
- WYSIWYG fields must use simple safe HTML: <p>, <ul>, <li>, and <strong> only.
- Write WYSIWYG fields in natural Indonesian, even if the flyer text is English.
- Contact fields must be plain scalar values, not HTML.
- social_media must be an array of objects using only these keys: {sorted(SOCIAL_MEDIA_KEYS)}.
- Typed fields must be raw integers. Deadline must be YYYY-MM-DD.
- Never use 0 as an unknown placeholder. Omit unknown numeric fields.
- status_pekerjaan must be exactly 0, 2, or 3. Use 0 for normal drafts.
- Use only controlled taxonomy terms from this options object. Omit terms that do not exist:
{json.dumps(allowed, ensure_ascii=False, indent=2)}
- Do not choose taxonomy values just because they are available. Only set a
  taxonomy when the flyer visibly says it or the role makes it unambiguous.
  In particular, omit pendidikan when education is not mentioned.

Output useful fields only. Include uncertain_fields for values that need human review.
{operator_instruction}
""".strip()
