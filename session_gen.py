"""Generate SESSION_STRING assistant (login akun Telegram sekali saja)."""
from __future__ import annotations

import asyncio
import getpass
import os

from dotenv import load_dotenv
from pyrogram import Client

load_dotenv()


async def main() -> None:
    api_id = os.environ.get("API_ID", "").strip()
    api_hash = os.environ.get("API_HASH", "").strip()
    if not api_id or not api_hash:
        api_id = input("API_ID: ").strip()
        api_hash = input("API_HASH: ").strip()

    print("\n=== Login akun assistant (akun kedua, bukan bot) ===")
    print("Pakai nomor HP akun yang akan join voice chat.\n")
    phone = input("Nomor HP (+62...): ").strip()

    client = Client(
        "musicem_session_gen",
        api_id=int(api_id),
        api_hash=api_hash,
        phone_number=phone,
        in_memory=True,
    )
    await client.connect()
    try:
        sent = await client.send_code(phone)
        code = input("Kode OTP dari Telegram: ").strip()
        try:
            await client.sign_in(phone, sent.phone_code_hash, code)
        except Exception:
            password = getpass.getpass("Password 2FA (kosongkan jika tidak ada): ")
            await client.check_password(password)

        session = await client.export_session_string()
        me = await client.get_me()
        print(f"\n✅ Login sebagai {me.first_name} ({me.id})")
        print("\nSalin baris ini ke .env:\n")
        print(f"SESSION_STRING={session}\n")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
