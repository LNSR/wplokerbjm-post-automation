from __future__ import annotations

import json
from typing import Any

from automation.payload.constants import (
    ACCEPTED_PAYLOAD_FIELDS,
    CONTROLLED_TAXONOMIES,
    INT_FIELDS,
    SOCIAL_MEDIA_KEYS,
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

Strictly follow these operator-provided skill instructions:
<skill>
{skill_markdown}
</skill>

STRICT JSON CONTRACT:
- The response object may use only these keys:
{json.dumps(accepted_fields + ["uncertain_fields"], ensure_ascii=False)}
- Do not add unsupported fields or invented facts.

Live taxonomy terms from WordPress backend — use only the exact term names listed:
{json.dumps(allowed, ensure_ascii=False, indent=2)}
{operator_instruction}
Output useful fields only. Include uncertain_fields for values that need human review.
""".strip()
