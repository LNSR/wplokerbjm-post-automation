<!-- Context: project-intelligence/concepts | Priority: critical | Version: 1.0 | Updated: 2026-06-15 -->

# Concept: WordPress Schema

**Purpose**: Core data model for `lowongan` custom post type — fields, taxonomies, and JobPosting mapping.

**Last Updated**: 2026-06-15

---

## Core Idea

WPLokerBJM uses CPT `lowongan` with MetaBox custom fields. Fields split into Typed (INT), WYSIWYG (HTML), Taxonomy (controlled terms), Contact, and Social Media. Validated by `NormalizedPayload` Pydantic model.

---

## Key Points

- **CPT**: `lowongan` — one post = one job listing
- **Title suffix**: `" | AI posted draft"` auto-appended — `constants.py:TITLE_SUFFIX`
- **INT fields**: `umur_min`, `umur_max`, `pengalaman`, `gaji_minimal`, `gaji_maksimal`, `status_pekerjaan`
- **WYSIWYG fields**: `tentang_perusahaan`, `deskripsi_pekerjaan`, `persyaratan`, `cara_melamar`, `benefit`
- **Default gender**: `"Pria/Wanita"` if not provided
- **Schema.org** JobPosting mapping for SEO rich snippets

---

## Controlled Taxonomies

| Taxonomy | Example Terms |
|----------|---------------|
| `kategori_lowongan` | Administrasi, Marketing, IT |
| `lokasi_pekerjaan` | Banjarmasin, Banjarbaru, Martapura |
| `jenis_pekerjaan` | Full Time, Part Time, Freelance |
| `gender` | Pria, Wanita, Pria/Wanita |
| `pendidikan` | SD, SMP, SMK/SMA, D3, S1 |

Source: `automation/payload/constants.py:CONTROLLED_TAXONOMIES`

---

## Quick Example

```python
NormalizedPayload(
    title="Staff Administrasi | AI posted draft",
    nama_perusahaan="PT Contoh Sejahtera",
    kategori_lowongan="Administrasi",
    lokasi_pekerjaan="Banjarmasin",
    umur_min=18, umur_max=35,
    gaji_minimal=2500000, gaji_maksimal=4000000,
    deskripsi_pekerjaan="<ul><li>Mengelola dokumen</li></ul>",
)
```

---

## 📂 Codebase References

**Model**: `automation/models.py:NormalizedPayload` — Pydantic model (all fields)
**Constants**: `automation/payload/constants.py` — `ACCEPTED_PAYLOAD_FIELDS`, `CONTROLLED_TAXONOMIES`, `WYSIWYG_FIELDS`, `INT_FIELDS`, `SOCIAL_MEDIA_KEYS`
**Normalization**: `automation/payload/normalize.py:normalize_payload()` — main pipeline; `normalize_taxonomy_value()` — term matching; `normalize_wysiwyg()` — HTML cleanup; `normalize_cara_melamar()` — contact linkification

---

## Related

- `guides/automation-workflows.md` — Pipeline flow
- `examples/payload-example.md` — Complete example
- `lookup/api-contracts.md` — Endpoints
