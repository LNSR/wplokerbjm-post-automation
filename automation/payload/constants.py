from __future__ import annotations


TITLE_SUFFIX = " | AI posted draft"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENCODE_CHAIN = (
    "go:kimi-k2.6:chat,"
    "go:kimi-k2.5:chat,"
    "go:mimo-v2.5:chat,"
    "go:minimax-m3:messages,"
    "go:qwen3.6-plus:messages,"
    "go:qwen3.7-plus:messages"
)
DEFAULT_COPYWRITER_CHAIN = "zen:mimo-v2.5-free:chat"
SOCIAL_MEDIA_KEYS = {
    "WhatsApp",
    "Instagram",
    "Facebook",
    "X / Twitter",
    "Threads",
    "TikTok",
    "LinkedIn",
    "Youtube",
    "Telegram",
}
CONTROLLED_TAXONOMIES = {
    "kategori_lowongan",
    "lokasi_pekerjaan",
    "jenis_pekerjaan",
    "gender",
    "pendidikan",
}
WYSIWYG_FIELDS = {
    "tentang_perusahaan",
    "deskripsi_pekerjaan",
    "persyaratan",
    "cara_melamar",
    "benefit",
}
ACCEPTED_PAYLOAD_FIELDS = {
    "title",
    "nama_perusahaan",
    "perusahaan",
    "kategori_lowongan",
    "lokasi_pekerjaan",
    "jenis_pekerjaan",
    "gender",
    "pendidikan",
    "umur_min",
    "umur_max",
    "pengalaman",
    "gaji_minimal",
    "gaji_maksimal",
    "deadline",
    "status_pekerjaan",
    "tentang_perusahaan",
    "deskripsi_pekerjaan",
    "persyaratan",
    "cara_melamar",
    "benefit",
    "email_kontak",
    "nomor_kontak",
    "situs_kontak",
    "social_media",
    "source",
}
INT_FIELDS = {
    "umur_min",
    "umur_max",
    "pengalaman",
    "gaji_minimal",
    "gaji_maksimal",
    "status_pekerjaan",
}
