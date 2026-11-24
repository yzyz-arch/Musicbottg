"""Login assistant tahap 1: minta kode OTP ke nomor HP.

Pemakaian:
    .venv/bin/python login_step1.py +62812xxxxxxx

Auth key disimpan di sesi disk (data/sessions/musicem_login.session) supaya
tahap 2 bisa lanjut di proses terpisah.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import config
from pyrogram import Client

SESSION_DIR = Path(__file__).resolve().parent / "data" / "sessions"
STATE = Path(__file__).resolve().parent / "data" / "login.json"


async def main(phone: str) -> int:
    if not config.API_ID or not config.API_HASH:
        print("API_ID/API_HASH belum diisi di .env")
        return 1

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    phone = phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        print("Nomor harus pakai kode negara, contoh: +6281234567890")
        return 1

    app = Client(
        "musicem_login",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        phone_number=phone,
        workdir=str(SESSION_DIR),
    )
    await app.connect()
    try:
        sent = await app.send_code(phone)
    except Exception as exc:
        print(f"GAGAL kirim kode: {exc}")
        return 1
    finally:
        await app.disconnect()

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps({"phone": phone, "phone_code_hash": sent.phone_code_hash}, indent=2)
    )
    STATE.chmod(0o600)
    print(f"KODE_DIKIRIM ke {phone}. Minta kode OTP dari Telegram, lalu jalankan tahap 2.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Pemakaian: python login_step1.py +628xxxxxxxx")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
