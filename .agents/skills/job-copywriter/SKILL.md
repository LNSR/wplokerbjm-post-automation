---
name: job-copywriter
description: >-
  Menyusun dan merapikan lowongan kerja WPLokerBJM dari OCR, flyer, chat,
  atau teks bebas menjadi field WordPress/Meta Box yang akurat, manusiawi,
  schema-first, dan siap ditampilkan di JobDetail.svelte. Gunakan skill ini
  untuk ekstraksi data lowongan, copywriting singkat berbahasa Indonesia,
  pemisahan field typed/taxonomy/WYSIWYG/contact/social media, dan validasi
  agar tidak menambah informasi spekulatif.
---

# Job Copywriter WPLokerBJM

## Goal

Ubah input lowongan kerja menjadi field yang siap dimasukkan ke sistem WPLokerBJM:

- Akurat terhadap sumber.
- Enak dibaca manusia.
- Sesuai schema WordPress/Meta Box.
- Tidak mengarang data.
- Tidak mengulang informasi di banyak field (DRY).

## Source Of Truth

Ikuti struktur data ini:

- UI detail: `JobDetail.svelte`
- Field WordPress/Meta Box: `CustomFields.php`
- Taxonomy: `Taxonomies.php`
- Frontend type: `MetaBox.ts`

Important:

- `ringkasanPekerjaan` bukan field input manual.
- `ringkasanPekerjaan` dibuat oleh UI/API dari taxonomy dan typed fields.
- Jangan output `ringkasanPekerjaan` sebagai field terpisah.

## Evidence Discipline

Lowongan otomatis harus mengutamakan bukti yang terlihat, bukan kelengkapan
narasi.

- Jika flyer buram, OCR tidak jelas, atau hanya sebagian teks terbaca,
  keluarkan payload yang lebih sedikit tetapi terverifikasi.
- Jangan membuat kalimat pengisi umum seperti "posisi ini bertanggung jawab",
  "mengikuti program rekrutmen", "bekerja pada penempatan yang ditentukan
  perusahaan", atau "lamaran dapat dikirimkan melalui tautan berikut" kecuali
  makna yang sama memang tertulis pada sumber.
- Jangan mengubah judul pekerjaan menjadi `deskripsi_pekerjaan`. Contoh:
  dari "Mobile App Developer" saja, jangan menulis "bertanggung jawab
  mengembangkan aplikasi mobile" kecuali tugas itu tertulis.
- Jangan membuat profil perusahaan dari logo/nama perusahaan saja.
  `tentang_perusahaan` hanya diisi jika profil perusahaan tertulis jelas atau
  sumber verifikasi resmi diberikan.
- Untuk `cara_melamar`, `email_kontak`, `nomor_kontak`, dan `situs_kontak`,
  hanya gunakan channel konkret yang terlihat: email, nomor telepon/WhatsApp,
  URL, hasil decode QR, atau alamat fisik. Jika QR terlihat tetapi tidak
  berhasil didecode, tandai sebagai tidak pasti, jangan mengarang link.
- Field yang tidak cukup bukti harus diomit, bukan dipoles.

## Output Contract

Output hanya field yang ada datanya dari input atau sumber terverifikasi. Hilangkan field kosong.

Untuk automation/REST ingest, output JSON **wajib** memakai key snake_case persis
di bawah ini. Jangan membuat alias, camelCase, atau sinonim bahasa Indonesia
seperti `kualifikasi`, `deskripsi`, `kontak`, `gaji`, `alamat`,
`lokasi_kerja`, `berkas_lamaran`, atau `info_lainnya`.

Mapping wajib:

- Kualifikasi, syarat, dokumen, skill kandidat -> `persyaratan`
- Tugas, tanggung jawab, scope kerja -> `deskripsi_pekerjaan`
- Cara daftar, alamat kirim lamaran, instruksi kontak -> `cara_melamar`
- Gaji/fasilitas/tunjangan non-angka -> `benefit`
- Gaji angka eksplisit -> `gaji_minimal` / `gaji_maksimal`
- WhatsApp/telepon -> `nomor_kontak`
- Email -> `email_kontak`
- Website/link pendaftaran -> `situs_kontak`
- Jangan isi angka `0` sebagai placeholder untuk field yang tidak diketahui.
  Omit field numerik yang tidak tertulis jelas.
- `status_pekerjaan` hanya boleh `0`, `2`, atau `3`; gunakan `0` untuk draft
  normal.
- Jangan memilih taxonomy hanya karena term tersedia di backend. Isi taxonomy
  hanya jika tertulis di sumber atau benar-benar tidak ambigu. Khusus
  `pendidikan`, omit jika pendidikan tidak disebutkan.

Gunakan format berikut:

```markdown
title:
nama_perusahaan:
perusahaan:
kategori_lowongan:
lokasi_pekerjaan:
jenis_pekerjaan:
gender:
pendidikan:
umur_min:
umur_max:
pengalaman:
gaji_minimal:
gaji_maksimal:
deadline:
status_pekerjaan:
tentang_perusahaan:
deskripsi_pekerjaan:
persyaratan:
cara_melamar:
benefit:
email_kontak:
nomor_kontak:
situs_kontak:
social_media:
```

Do not include a field if the value is unknown.

Clone/storage note:

- `email_kontak`, `nomor_kontak`, and `situs_kontak` are cloned scalar fields;
  multiple values may be comma-separated in copywriter output.
- `social_media` is a Meta Box cloned `fieldset_text`. For human-readable
  copywriter output, use `Platform: value; Platform: value`. For automated
  posting, convert it to an array of platform objects, e.g.
  `[{"WhatsApp":"+6287844665424","Instagram":"loker_banjarmasin"}]`.

## Field Groups

### Identity Fields

`title`

- Job title.
- Use a short, searchable title.
- Multiple positions: join with `&`.
- For automated AI draft posting, append ` | AI posted draft` to the final
  post title so human reviewers can distinguish generated drafts.
- Example: `Barista & Kitchen`.

`nama_perusahaan`

- Official company, shop, outlet, or brand name.
- Keep formal capitalization.
- Do not invent `PT`, `CV`, or legal suffixes if not shown.
- If taxonomy `perusahaan` is also used, keep the value consistent.

`perusahaan`

- Taxonomy value for company.
- Usually same as `nama_perusahaan`.
- Use only when the system/user expects taxonomy terms.

### Taxonomy Fields

Use plain text terms. Multiple values may be comma-separated if needed.

`kategori_lowongan`

- Job category, e.g. `Food & Beverage`, `Admin`, `Sales`, `Teknisi`.
- Infer only when obvious from the role.

`lokasi_pekerjaan`

- Work location, e.g. `Banjarmasin`, `Banjarbaru`, `Remote`.
- Do not put a full street address here unless the existing taxonomy uses full addresses.
- Full address can go in `cara_melamar` only if it is part of application instructions.

`jenis_pekerjaan`

- Employment/work arrangement.
- Examples: `Full-time`, `Part-time`, `Freelance`, `Magang`, `On-site`, `Remote`, `Hybrid`.
- Use only if present or very clear.

`gender`

- Use the explicitly required gender when the flyer mentions it.
- If the flyer does not mention gender, assume the role is open to all genders
  and output `Pria/Wanita` so both gender taxonomy checkboxes can be assigned.
- Examples: `Pria`, `Wanita`, `Pria/Wanita`.

`pendidikan`

- Education requirement.
- Must be an exact match from the available taxonomy options provided in the prompt. The allowed options are fetched live from the WordPress backend — you will see them listed in the system prompt.

### Typed Fields

Typed fields must contain raw machine-friendly values.

`umur_min`

- Number only.
- Example: `18`.

`umur_max`

- Number only.
- Example: `30`.

`pengalaman`

- Number of years only.
- Example: use `2`, not `2 tahun`.
- If the source says `fresh graduate`, omit this field unless the system supports `0`.

`gaji_minimal`

- Number only, no `Rp`, no dots, no commas.
- Example: `2500000`.

`gaji_maksimal`

- Number only, no `Rp`, no dots, no commas.
- Example: `3500000`.

`deadline`

- Date only in `YYYY-MM-DD`.
- If the source date is ambiguous, omit or mark as needs verification outside the field value.

`status_pekerjaan`

- Use only one of:
  - `0` = Normal
  - `2` = Urgent 
  - `3` = Pinned
- Default to `0`.
  - When less than 14 days left set to `2` unless the source says otherwise.
  

### WYSIWYG Fields

These fields accept safe, simple HTML.

Allowed structure:

```html
<p>Short paragraph.</p>
<ul>
  <li>One clear point.</li>
  <li>Another clear point.</li>
</ul>
```

Rules:

- Do not include section headings like "Persyaratan" or "Cara Melamar"; the UI already renders headings.
- Use `<p>` for short prose.
- Use `<ul><li>` when there are 2 or more points.
- Keep each bullet to one idea.
- Avoid decorative HTML, inline styles, scripts, iframes, and unnecessary attributes.

`tentang_perusahaan`

- 1 short paragraph.
- Only write when company profile is present or verified.
- Do not use generic filler like "perusahaan yang terus berkembang" unless the source says so.
- A logo, brand name, or recruitment poster alone is not enough evidence for
  `tentang_perusahaan`.

Good:

```html
<p>Kopi Senja adalah kedai kopi di Banjarmasin yang melayani minuman kopi, non-kopi, dan makanan ringan untuk pelanggan harian.</p>
```

`deskripsi_pekerjaan`

- Daily tasks, responsibilities, and work scope.
- Put operational action here, not candidate qualities.
- If the source has no task details, omit this field.
- Do not infer duties from the job title. For example, "Mobile App Developer"
  alone is not evidence for "mengembangkan aplikasi mobile".

Good:

```html
<ul>
  <li>Menyiapkan minuman dan makanan sesuai standar outlet.</li>
  <li>Melayani pelanggan dengan ramah dan cepat.</li>
  <li>Menjaga kebersihan area kerja dan peralatan.</li>
</ul>
```

`persyaratan`

- Candidate requirements and qualifications.
- Include age, gender, education, domicile, experience, skill, documents, and personality traits here.
- If a value is already extracted into typed/taxonomy fields, it may still appear here when useful for humans, but keep it concise.

Good:

```html
<ul>
  <li>Pria/Wanita, usia maksimal 30 tahun.</li>
  <li>Pendidikan minimal SMA/SMK sederajat.</li>
  <li>Berpengalaman minimal 2 tahun di bidang terkait.</li>
  <li>Domisili Banjarmasin dan sekitarnya.</li>
</ul>
```

`cara_melamar`

- Clear application steps.
- Include application deadline only if it belongs naturally in instructions.
- Link email, WhatsApp, website, and social media only when the source provides them or they are verified.

Good:

```html
<p>Kirim CV melalui WhatsApp ke <a rel="noopener noreferrer nofollow" href="https://wa.me/6287757132074">+62 877-5713-2074</a>.</p>
```

`benefit`

- Benefits, facilities, compensation notes, or employee perks.
- Do not move location/maps into `benefit`.

Good:

```html
<ul>
  <li>Gaji pokok.</li>
  <li>Bonus kinerja.</li>
  <li>Makan karyawan.</li>
</ul>
```

### Contact Fields

`email_kontak`

- Email address only.
- Multiple values: comma-separated.
- Example: `hr@example.com, career@example.com`.

`nomor_kontak`

- Phone number only.
- Multiple values: comma-separated.
- Keep valid characters: digits, `+`, spaces, hyphen.
- Example: `+6287757132074, +6281255511122`.

`situs_kontak`

- Full URL only.
- Must include `https://` when available.
- Multiple values: comma-separated.

### Social Media Field

`social_media`

Use this exact string shape:

```text
Instagram: kopisenja; WhatsApp: +6287757132074; TikTok: kopisenja
```

Allowed platform names:

- `WhatsApp`
- `Instagram`
- `Facebook`
- `X / Twitter`
- `Threads`
- `TikTok`
- `LinkedIn`
- `Youtube`
- `Telegram`

Rules:

- Use username without `@` when possible.
- Full links are acceptable if the input gives full links.
- For WhatsApp in `social_media`, prefer `+62...`.
- Do not create social links from an unclear handle.
- When sending to the WordPress ingest endpoint, transform this display string
  into the cloned fieldset array shape described near the Output Contract.

## Link Rules For WYSIWYG

Only WYSIWYG fields use clickable HTML links.

Website:

```html
<a rel="noopener nofollow noreferrer" href="https://example.com/karir">Website Karir</a>
```

Email:

```html
<a rel="noopener nofollow noreferrer" href="mailto:hr@example.com">hr@example.com</a>
```

WhatsApp:

```html
<a rel="noopener nofollow noreferrer" href="https://wa.me/6287757132074">+62 877-5713-2074</a>
```

Instagram:

```html
<a rel="noopener nofollow noreferrer" href="https://www.instagram.com/kopisenja">@kopisenja</a>
```

Rules:

- Convert local Indonesian WhatsApp numbers starting with `0` to `62` in `wa.me`.
- Do not create Google Maps links unless the source provides a valid maps link or the location is verified.
- Avoid long raw URLs in visible text. Prefer labels like `Website Karir` or account names.

## Writing Style

Use natural Indonesian.

Preferred style:

- Professional but warm.
- Short sentences.
- Concrete verbs.
- No hype.
- No corporate filler.
- No excessive rewriting that changes meaning.

Avoid:

- "Bergabunglah dengan tim kami yang dinamis..."
- "Perusahaan yang sedang berkembang pesat..."
- "Kandidat akan berperan penting..."
- Long paragraphs copied from flyer OCR.
- Repeating the same phone/email in too many fields.

Good rewrite patterns:

- Source: `jujur rajin disiplin`
- Output: `<li>Jujur, rajin, dan disiplin.</li>`

- Source: `bisa kerja team`
- Output: `<li>Mampu bekerja sama dalam tim.</li>`

- Source: `bertanggung jawab atas kebersihan outlet`
- Output in `deskripsi_pekerjaan`: `<li>Menjaga kebersihan outlet selama jam kerja.</li>`

## Extraction Rules

Map common flyer/OCR labels:

- `We Are Hiring`, `Open Recruitment` -> ignore as decoration.
- Main role text -> `title`.
- Company/brand/logo text -> `nama_perusahaan` and possibly `perusahaan`.
- `Syarat`, `Kualifikasi`, `Requirements` -> `persyaratan`.
- `Jobdesk`, `Tugas`, `Responsibilities` -> `deskripsi_pekerjaan`.
- `Benefit`, `Fasilitas` -> `benefit`.
- `Kirim CV`, `Apply`, `Hubungi`, `Send your resume` -> `cara_melamar`.
- `WA`, `WhatsApp`, phone for application -> `nomor_kontak`, optionally `social_media`, and link in `cara_melamar`.
- `Email` -> `email_kontak`.
- `IG`, `Instagram` -> `social_media`.
- `Lokasi`, `Penempatan`, `Domisili` -> `lokasi_pekerjaan` if it is work location; `persyaratan` if it is domicile requirement.

## Multi-Position Rules

When one source contains multiple positions:

- `title`: combine positions with `&`.
- Shared requirements: write once under "Berlaku untuk semua posisi".
- Position-specific requirements/tasks: group with a short `<p><strong>Position:</strong></p>` before the list.
- Do not duplicate identical bullets under every position.

Example:

```html
<p><strong>Berlaku untuk semua posisi:</strong></p>
<ul>
  <li>Usia 18-28 tahun.</li>
  <li>Domisili Banjarmasin.</li>
</ul>
<p><strong>Crew:</strong></p>
<ul>
  <li>Pria.</li>
  <li>Pendidikan minimal SMA/sederajat.</li>
</ul>
<p><strong>Kasir:</strong></p>
<ul>
  <li>Wanita.</li>
  <li>Mampu mengoperasikan komputer.</li>
</ul>
```

## Verification And Enrichment

Default rule: use only the input.

Allowed enrichment:

- Use verified official sources only when available in the working environment.
- Accept official website, official social media, official Google Maps, or explicit user-provided reference.
- If unsure, omit the field.

Do not:

- Mention or require unavailable tools.
- Invent company profiles, maps links, salaries, deadlines, or social media.
- Add fields not present in the Output Contract.

If verification is not possible, write only what can be supported by the input.

## Final QA Checklist

Before final output, check:

- No `ringkasanPekerjaan` field is output.
- Typed fields contain raw numbers/dates only.
- WYSIWYG fields use simple safe HTML.
- No UI section headings are repeated inside WYSIWYG content.
- Contact fields contain plain contact values, not HTML.
- `social_media` uses allowed platform names and `Platform: value; Platform: value` format.
- No invented facts.
- No duplicate information unless it helps human readability.

## Minimal Example

Input:

```text
WE ARE HIRING
BARISTA & KITCHEN
Kopi Senja
Syarat:
- Domisili Banjarmasin
- Laki-laki/Perempuan
- Usia max 30 tahun
- Punya 2 tahun pengalaman
Hubungi WA +62 877-5713-2074
```

Output:

```markdown
title: Barista & Kitchen
nama_perusahaan: Kopi Senja
perusahaan: Kopi Senja
lokasi_pekerjaan: Banjarmasin
gender: Pria/Wanita
umur_max: 30
pengalaman: 2
persyaratan:
<ul>
  <li>Domisili Banjarmasin.</li>
  <li>Pria/Wanita, usia maksimal 30 tahun.</li>
  <li>Berpengalaman minimal 2 tahun di bidang terkait.</li>
</ul>
cara_melamar:
<p>Kirim lamaran melalui WhatsApp ke <a rel="noopener nofollow noreferrer" href="https://wa.me/6287757132074">+62 877-5713-2074</a>.</p>
nomor_kontak: +6287757132074
social_media: WhatsApp: +6287757132074
status_pekerjaan: 0
```
