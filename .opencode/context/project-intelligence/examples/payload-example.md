<!-- Context: project-intelligence/examples | Priority: high | Version: 1.0 | Updated: 2026-06-15 -->

# Example: NormalizedPayload

**Purpose**: Complete reference payload showing all fields for a WPLokerBJM job posting.

**Last Updated**: 2026-06-15

---

## Use Case

After AI extracts data from a flyer and `normalize_payload()` validates it, this is the final JSON shape POSTed to WordPress. Useful for building test fixtures or verifying endpoints.

---

## Code

```json
{
  "title": "Lowongan Staff Administrasi | AI posted draft",
  "nama_perusahaan": "PT Contoh Sejahtera",
  "kategori_lowongan": "Administrasi",
  "lokasi_pekerjaan": "Banjarmasin",
  "jenis_pekerjaan": "Full Time",
  "gender": "Pria/Wanita",
  "pendidikan": "SMK/SMA",
  "umur_min": 18,
  "umur_max": 35,
  "pengalaman": 1,
  "gaji_minimal": 2500000,
  "gaji_maksimal": 4000000,
  "deadline": "2026-07-15",
  "status_pekerjaan": 0,
  "tentang_perusahaan": "<p>Perusahaan jasa logistik.</p>",
  "deskripsi_pekerjaan": "<ul><li>Mengelola dokumen administrasi</li><li>Input data</li></ul>",
  "persyaratan": "<ul><li>Pengalaman 1 tahun</li><li>Teliti</li></ul>",
  "cara_melamar": "<p>Kirim CV ke</p> <a href=\"mailto:hrd@contoh.com\">hrd@contoh.com</a>",
  "benefit": "<ul><li>BPJS Kesehatan</li><li>Tunjangan makan</li></ul>",
  "email_kontak": "hrd@contoh.com",
  "nomor_kontak": "+6281234567890",
  "social_media": [{"Instagram": "contoh_sejahtera"}],
  "source": "flyers/flyer-001.jpg"
}
```

---

## Explanation

1. **Title**: Auto-appended suffix `" | AI posted draft"` — `TITLE_SUFFIX`
2. **Taxonomies**: Must match backend terms exactly — validated by `normalize_taxonomy_value()`
3. **INT fields**: `umur_min`, `gaji_minimal` etc.; non-positive values omitted
4. **WYSIWYG**: HTML `<ul>/<li>` for lists; `cara_melamar` auto-linkifies contacts
5. **Social media**: Keys limited to `SOCIAL_MEDIA_KEYS` set
6. **Defaults**: `status_pekerjaan=0`, `gender="Pria/Wanita"` if missing

---

## 📂 Codebase References

**Model**: `automation/models.py:NormalizedPayload` — Pydantic definition
**Normalizer**: `automation/payload/normalize.py:normalize_payload()`
**Constants**: `automation/payload/constants.py` — field sets

---

## Related

- `concepts/wordpress-schema.md` — Data model
- `lookup/api-contracts.md` — Endpoint that accepts this payload
- `errors/common-errors.md` — Validation failures
