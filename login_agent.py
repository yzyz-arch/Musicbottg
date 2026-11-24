"""Agent login assistant: satu proses, satu koneksi, kode OTP dibaca dari file.

Dipakai karena Telegram mengikat kode konfirmasi ke auth key/koneksi yang
memintanya. Proses ini tetap connected sambil menunggu kode.

Jalankan:
    nohup .venv/bin/python -u login_agent.py +628xxx > login_agent.log 2>&1 &

Lalu taruh kode OTP ke data/otp.txt (dan password 2FA ke data/2fa.txt).
Hasil ditulis ke data/login_result.txt, SESSION_STRING otomatis masuk ke .env.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import config
from pyrogram import Client
from pyrogram.errors import FloodWait, PhoneNumberInvalid, SessionPasswordNeeded

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SESSIONS = DATA / "sessions"
OTP_FILE = DATA / "otp.txt"
PASS_FILE = DATA / "2fa.txt"
RESULT = DATA / "login_result.txt"
STATE = DATA / "login_state.json"
ENV = BASE / ".env"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save_session(session: str) -> None:
    text = ENV.read_text()
    if re.search(r"(?m)^SESSION_STRING=", text):
        text = re.sub(r"(?m)^SESSION_STRING=.*$", f"SESSION_STRING={session}", text)
    else:
        text += f"\nSESSION_STRING={session}\n"
    ENV.write_text(text)
    ENV.chmod(0o600)


async def main(phone: str) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    SESSIONS.mkdir(parents=True, exist_ok=True)
    for f in (OTP_FILE, PASS_FILE, RESULT):
        f.unlink(missing_ok=True)

    app = Client(
        "musicem_agent",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        phone_number=phone,
        workdir=str(SESSIONS),
    )
    await app.connect()

    try:
        sent = await app.send_code(phone)
    except FloodWait as exc:
        log(f"FLOOD_WAIT {exc.value}s — Telegram minta tunggu sebelum kirim kode lagi")
        await app.disconnect()
        return 3
    except PhoneNumberInvalid:
        log("NOMOR_INVALID")
        await app.disconnect()
        return 1

    STATE.write_text(json.dumps({"phone": phone, "sent_at": int(time.time())}, indent=2))
    STATE.chmod(0o600)
    log(f"CODE_SENT ke {phone} — menunggu OTP di {OTP_FILE.name} (maks 10 menit)")

    deadline = time.time() + 600
    signed_in = False
    while time.time() < deadline:
        if OTP_FILE.exists():
            code = OTP_FILE.read_text().strip()
            OTP_FILE.unlink(missing_ok=True)
            try:
                await app.sign_in(phone, sent.phone_code_hash, code)
                signed_in = True
                break
            except SessionPasswordNeeded:
                log("BUTUH_2FA — taruh password di data/2fa.txt")
                while time.time() < deadline and not PASS_FILE.exists():
                    await asyncio.sleep(2)
                if PASS_FILE.exists():
                    await app.check_password(PASS_FILE.read_text().strip())
                    PASS_FILE.unlink(missing_ok=True)
                    signed_in = True
                    break
                log("TIMEOUT_2FA")
                return 2
            except Exception as exc:
                log(f"OTP_GAGAL: {exc}")
                RESULT.write_text(f"FAIL {exc}\n")
                # tetap connected: kode berikutnya bisa dicoba (selama belum expired)
        await asyncio.sleep(2)

    if not signed_in:
        log("TIMEOUT tanpa login")
        RESULT.write_text("FAIL timeout\n")
        await app.disconnect()
        return 2

    me = await app.get_me()
    session = await app.export_session_string()
    save_session(session)
    line = f"LOGIN_OK {me.first_name} ({me.id}) — SESSION_STRING tersimpan di .env"
    RESULT.write_text(line + "\n")
    log(line)
    await app.disconnect()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Pemakaian: python login_agent.py +628xxxxxxxx")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1].strip())))
