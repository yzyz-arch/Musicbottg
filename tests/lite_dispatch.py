"""Tes dispatch mode lite tanpa jaringan: /start, /id, /song, callback."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lite import LiteBot, register  # noqa: E402

sent: list[tuple[str, dict]] = []


async def fake_call(method: str, **params):
    sent.append((method, params))
    if method == "sendMessage":
        return {
            "message_id": len(sent),
            "chat": {"id": params.get("chat_id"), "type": "private"},
            "text": params.get("text", ""),
        }
    if method == "editMessageText":
        return {
            "message_id": params.get("message_id", 1),
            "chat": {"id": params.get("chat_id"), "type": "private"},
            "text": params.get("text", ""),
        }
    return True


def update(text: str, chat_id: int = 123456789) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "first_name": "SYNS", "username": "syns"},
            "text": text,
        },
    }


async def main() -> int:
    import database as db

    await db.init()
    bot = LiteBot("TEST")
    bot.call = fake_call
    bot.username = "MusicyzBot"
    register(bot)

    ok = True

    async def expect(label: str, update_data: dict, method: str, contains: str = "") -> None:
        nonlocal ok
        sent.clear()
        await bot._dispatch(update_data)
        hit = [p for m, p in sent if m == method]
        good = bool(hit) and (contains in str(hit[0]) if contains else True)
        ok &= good
        print(f"{'✅' if good else '❌'} {label} → {method}: {str(hit[0])[:90] if hit else 'TIDAK ADA'}")

    await expect("/start", update("/start"), "sendMessage", "Musicem")
    await expect("/help", update("/help"), "sendMessage", "Menu Perintah")
    await expect("/id", update("/id"), "sendMessage", "123456789")
    await expect("/ping", update("/ping"), "sendMessage")
    await expect("command@bot", update("/start@MusicyzBot"), "sendMessage")
    await expect("/song tanpa argumen", update("/song"), "sendMessage", "Kasih judul")

    sent.clear()
    await bot._dispatch(
        {
            "update_id": 2,
            "callback_query": {
                "id": "cb1",
                "from": {"id": 1, "first_name": "X"},
                "data": "help",
                "message": {
                    "message_id": 9,
                    "date": 0,
                    "chat": {"id": 1, "type": "private"},
                    "text": "x",
                },
            },
        }
    )
    cb_ok = any(m == "answerCallbackQuery" for m, _ in sent)
    ok &= cb_ok
    print(f"{'✅' if cb_ok else '❌'} callback help → answerCallbackQuery")

    print("\n" + ("MODE LITE OK" if ok else "MODE LITE GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
