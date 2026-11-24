# 🎧 Musicem Bot

Bot musik Telegram dengan streaming **voice chat realtime** (py-tgcalls + ntgcalls),
pencarian YouTube, antrean per grup, panel kontrol inline, dan database SQLite.

Fitur mengikuti bot musik premium pada umumnya: `/play`, `/vplay`, `/song`,
pause/resume/skip/seek/loop/volume, antrean berpaginasi, kontrol tombol,
auth user, auto-leave, cache download, dan statistik.

---

## 0. Mode jalan

**Default sekarang: MODE FILE — tanpa voice chat.** Lagu/video dikirim langsung
sebagai file (audio MP3 / video MP4), bisa di grup maupun DM.

| Mode | Syarat | Kemampuan |
|---|---|---|
| **file** (default, `VOICE_CHAT=false`) | `BOT_TOKEN` + `API_ID` + `API_HASH` | `/play` `/vplay` kirim file, `/song`, tombol pilih hasil, `/start` `/help` `/ping` `/id` `/stats` |
| **voice chat** (`VOICE_CHAT=true`) | + `SESSION_STRING` (akun assistant) | streaming VC: pause/resume/skip/seek/loop/volume/queue |
| **lite** | cukup `BOT_TOKEN` | versi ringkas mode file (dipakai kalau `API_ID`/`API_HASH` belum ada) |

Set `VOICE_CHAT=true` di `.env` kalau nanti mau streaming voice chat.
Paksa mode lite dengan `MODE=lite`.

## 1. Yang dibutuhkan

| Komponen | Keterangan |
|---|---|
| `API_ID` / `API_HASH` | https://my.telegram.org → *API development tools* (wajib, milik akun kamu) |
| `BOT_TOKEN` | sudah terisi di `.env` |
| `SESSION_STRING` | akun **user** (assistant) yang join voice chat — bot tidak bisa join VC sendiri |
| Python 3.10+ | 3.14 sudah dites |
| ffmpeg + ffprobe | `apt install ffmpeg` |

> Bot **tidak bisa** streaming ke voice chat tanpa akun assistant. Akun assistant
> cukup akun Telegram biasa (boleh akun kedua), harus jadi anggota grup.

## 1b. Aktivasi ulang (kalau bot mati / pindah server)

```bash
git clone https://github.com/yzyz-arch/Musicbottg.git && cd Musicbottg
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo apt install -y ffmpeg
cp .env.example .env        # isi BOT_TOKEN, API_ID, API_HASH, OWNER_ID
./start.sh                  # cek: tail -f bot.log
```

Yang wajib diisi minimal: `BOT_TOKEN` + `API_ID` + `API_HASH` (mode file, tanpa VC).
Kalau `API_ID`/`API_HASH` belum ada, bot tetap jalan di mode lite pakai token saja.

## 2. Instalasi

```bash
cd musicem-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo apt install -y ffmpeg
```

Isi `.env`:

```env
API_ID=123456
API_HASH=xxxxxxxxxxxxxxxxxxxxxxxx
BOT_TOKEN=...            # sudah ada
OWNER_ID=123456789      # sudah ada
SESSION_STRING=...       # langkah 3
```

## 3. Buat session assistant

```bash
.venv/bin/python session_gen.py
```

Masukkan nomor HP akun assistant → kode OTP → (password 2FA bila ada).
Salin `SESSION_STRING=...` yang muncul ke `.env`.

## 4. Jalankan

```bash
.venv/bin/python bot.py
```

Kalau muncul `bot online: @username` (mode full) atau
`mode lite aktif sebagai @username`, berarti siap.

Jalankan di background:

```bash
./start.sh          # nyalakan (nohup, log ke bot.log)
./stop.sh           # matikan
```

Cek cepat tanpa Telegram:

```bash
.venv/bin/python tests/selftest.py
```

## 5. Pasang ke grup / pakai di DM

1. Tambahkan bot ke grup (admin tidak wajib untuk mode file, tapi disarankan
   supaya bisa hapus pesan & kirim file besar).
2. Di grup, perintah harus dipanggil dengan username kalau *privacy mode* bot
   masih aktif: `/play@MusicyzBot judul`. Matikan privacy lewat @BotFather →
   `/setprivacy` → Disable supaya cukup `/play judul`.
3. DM langsung ke bot juga bisa: `/play judul lagu`.

```
/play perfect ed sheeran
/vplay lofi hip hop
/song bohemian rhapsody
```

## 6. Perintah

| Perintah | Fungsi |
|---|---|
| `/play <judul\|link>` | Cari lalu putar audio di VC |
| `/vplay <judul\|link>` | Putar video (maks 720p) |
| `/song <judul\|link>` | Download & kirim MP3 |
| `/pause` / `/resume` | Pause / lanjut |
| `/skip` | Lagu berikutnya |
| `/seek 1:30` | Lompat ke posisi |
| `/end` | Stop & bersihkan antrean |
| `/loop off\|one\|all` | Mode ulang |
| `/volume 1-200` | Volume (via filter ffmpeg) |
| `/queue` `/current` | Antrean & lagu aktif |
| `/auth` `/unauth` `/sudoers` | Kelola user yang boleh kontrol |
| `/stats` `/id` `/ping` | Info bot |

Hak kontrol: **owner**, **sudo**, **admin grup**, atau user yang di-`/auth`.
Siapa pun anggota grup boleh menambah lagu ke antrean.

## 7. Struktur

```
bot.py              entrypoint (Pyrogram bot + assistant + PyTgCalls)
config.py           semua env
database.py         SQLite async (chat, user, auth, setting, counter)
downloader.py       yt-dlp search/download + cache
queue_manager.py    state antrean per chat
player.py           mesin playback (play/pause/seek/loop/auto-next)
plugins/            handler Telegram (play, controls, callbacks, admin, tools)
strings.py          semua teks pesan
utils.py            format, auth, markup
session_gen.py      generator SESSION_STRING
tests/selftest.py   tes tanpa koneksi Telegram
```

## 8. Deploy (systemd)

```bash
sudo cp deploy/musicem-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now musicem-bot
journalctl -u musicem-bot -f
```

## 9. Docker

```bash
docker build -t musicem-bot .
docker run -d --env-file .env -v "$PWD/data:/app/data" -v "$PWD/downloads:/app/downloads" musicem-bot
```

## 10. Troubleshooting

| Gejala | Penyebab / solusi |
|---|---|
| `Assistant belum bisa join` | Bot belum admin / belum punya izin *Invite Users* |
| `NoActiveGroupCall` | Voice chat belum dimulai (atau bot bukan admin) |
| Download gagal / “Sign in to confirm” | IP datacenter diblok YouTube → isi `cookies.txt` (export dari browser) dan set `COOKIES_FILE` |
| Suara tidak keluar | Assistant tidak ada di grup, atau akun assistant dibatasi Telegram |
| `TooOldPyrogramVersion` | Pakai `requirements.txt` (kurigram 2.2.x) |
| Streaming tidak jalan / `/play` cuma kirim file | Itu mode file (`VOICE_CHAT=false`). Set `VOICE_CHAT=true` + isi `SESSION_STRING` untuk VC |
| File gagal terkirim, > 20 MB | Batas upload bot biasa 20–50 MB; kecilkan `VIDEO_HEIGHT` atau kirim link |
| `Conflict: terminated by other getUpdates` | Ada instance lain dengan token sama — matikan dulu (full & lite tidak boleh bareng) |

## 11. Catatan

- File download disimpan di `downloads/` dan dibersihkan otomatis setelah `CACHE_TTL`.
- Volume diimplementasikan lewat filter ffmpeg (`volume=x`) karena ntgcalls 3.x
  belum punya API volume langsung; perubahan volume me-restart stream dari posisi
  terakhir.
- Token bot yang dibagikan lewat chat sebaiknya di-*revoke* di @BotFather lalu
  ganti dengan token baru.
