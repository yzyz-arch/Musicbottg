"""Login assistant tahap 2: verifikasi OTP (dan password 2FA) → SESSION_STRING.

Pemakaian:
    .venv/bin/python login_step2.py 12345
    .venv/bin/python login_step2.py 12345 "password-2fa"

SESSION_STRING hasilnya ditulis otomatis ke .env.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import config
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded

BASE = Path(__file__).resolve().parent
SESSION_DIR = BASE / "data" / "sessions"
STATE = BASE / "data" / "login.json"
ENV = BASE / ".env"


def save_session(session: str) -> None:
    text = ENV.read_text()
    if re.search(r"(?m)^SESSION_STRING=", text):
        text = re.sub(r"(?m)^SESSION_STRING=.*$", f"SESSION_STRING={session}", text)
    else:
        text += f"\nSESSION_STRING={session}\n"
    ENV.write_text(text)
    ENV.chmod(0o600)


async def main(code: str, password: str | None) -> int:
    if not STATE.exists():
        print("Belum ada permintaan kode. Jalankan login_step1.py dulu.")
        return 1
    state = json.loads(STATE.read_text())
    phone = state["phone"]

    app = Client(
        "musicem_login",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        phone_number=phone,
        workdir=str(SESSION_DIR),
    )
    await app.connect()
    try:
        try:
            await app.sign_in(phone, state["phone_code_hash"], code)
        except SessionPasswordNeeded:
            if not password:
                print("BUTUH_PASSWORD: akun pakai 2FA. Jalankan ulang dengan password.")
                return 2
            await app.check_password(password)
        me = await app.get_me()
        session = await app.export_session_string()
    except Exception as exc:
        print(f"GAGAL login: {exc}")
        return 1
    finally:
        await app.disconnect()

    save_session(session)
    STATE.unlink(missing_ok=True)
    print(f"LOGIN_OK sebagai {me.first_name} ({me.id}) — SESSION_STRING tersimpan di .env")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Pemakaian: python login_step2.py <kode-otp> [password-2fa]")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1].strip(), sys.argv[2] if len(sys.argv) > 2 else None)))
