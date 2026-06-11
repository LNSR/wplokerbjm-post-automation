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


def raw_facts_schema() -> dict[str, Any]:
    string_fields = [
        "title",
        "company",
        "company_profile",
        "location_text",
        "employment_type",
        "gender",
        "education",
        "deadline_text",
        "status_hint",
        "apply_url",
        "email",
        "phone",
        "website",
        "application_instructions",
    ]
    int_fields = ["age_min", "age_max", "experience_years", "salary_min", "salary_max"]
    list_fields = ["responsibilities", "requirements", "benefits", "social_media", "uncertain_fields"]
    properties: dict[str, Any] = {
        field: {"type": "STRING", "nullable": True} for field in string_fields
    }
    properties.update({field: {"type": "INTEGER", "nullable": True} for field in int_fields})
    properties.update(
        {
            field: {
                "type": "ARRAY",
                "nullable": True,
                "items": {"type": "STRING"},
            }
            for field in list_fields
        }
    )
    return {"type": "OBJECT", "properties": properties}


def build_raw_facts_prompt(
    options: dict[str, Any],
    custom_instruction: str | None = None,
) -> str:
    operator_instruction = ""
    if custom_instruction:
        operator_instruction = f"""

Optional instruction for this flyer:
<operator_instruction>
{json.dumps(custom_instruction, ensure_ascii=False)}
</operator_instruction>
Follow it only when compatible with visible flyer evidence. Do not invent missing facts.
"""

    return f"""
You are Agent 1 in a two-stage WPLokerBJM extraction pipeline.

Your only job is to read the Indonesian job vacancy flyer image and return raw visible facts.
Do not write final WordPress copy. Do not write HTML. Do not infer salary, deadline,
benefits, education, experience, or job type unless visible or unambiguous from the flyer.

Return only one JSON object. Use these raw-fact keys when evidence exists:
{json.dumps(list(raw_facts_schema()["properties"].keys()), ensure_ascii=False)}

Use arrays for responsibilities, requirements, benefits, social_media, and uncertain_fields.
Use null or omit unknown fields. Include uncertain_fields for low-confidence visible facts only.
{operator_instruction}
""".strip()


def build_copywriter_prompt(
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
Follow this instruction only when compatible with raw facts, visible evidence, taxonomy restrictions, and safety rules.
"""

    return f"""
You are Agent 2 in a two-stage WPLokerBJM extraction pipeline.

Convert raw flyer facts into a final WordPress/Meta Box JSON payload.
Return only one JSON object. Do not wrap it in markdown.

Strictly follow these operator-provided skill instructions:
<skill>
{skill_markdown}
</skill>

STRICT JSON CONTRACT:
- The response object may use only these keys:
{json.dumps(accepted_fields + ["uncertain_fields"], ensure_ascii=False)}
- Use only the raw facts provided by Agent 1. Do not invent facts.
- Write WYSIWYG fields as safe simple HTML.
- Link email, website, and WhatsApp in cara_melamar with <a rel="noopener nofollow noreferrer" href="...">.

Live taxonomy terms from WordPress backend — use only exact term names listed:
{json.dumps(allowed, ensure_ascii=False, indent=2)}
{operator_instruction}
""".strip()


def build_copywriter_user_text(raw_facts: dict[str, Any]) -> str:
    return f"""
Convert these raw flyer facts into the final WPLokerBJM JSON contract.

<raw_facts>
{json.dumps(raw_facts, ensure_ascii=False, indent=2)}
</raw_facts>
""".strip()


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
