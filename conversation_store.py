"""
conversation_store.py — Multi-turn conversation memory untuk Gemini AI.
Simpan history chat per user dengan TTL 1 jam (reset setelah idle).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MAX_HISTORY   = 10          # Maks 10 pasang pesan (user+bot) per session
SESSION_TTL   = 60          # Menit — reset history jika idle lebih dari ini
MAX_MSG_CHARS = 800         # Potong pesan panjang agar tidak overflow context


class ConversationStore:
    """
    In-memory conversation history per user_id.
    Format history: list of {"role": "user"|"model", "parts": [{"text": "..."}]}
    — sesuai format Gemini multi-turn API.
    """

    def __init__(self) -> None:
        # {user_id: {"history": [...], "last_active": datetime}}
        self._sessions: dict[str, dict] = defaultdict(lambda: {
            "history":     [],
            "last_active": datetime.now(),
        })

    def _cleanup_expired(self) -> None:
        cutoff = datetime.now() - timedelta(minutes=SESSION_TTL)
        expired = [uid for uid, s in self._sessions.items() if s["last_active"] < cutoff]
        for uid in expired:
            del self._sessions[uid]
            logger.debug(f"[conv] session expired: {uid}")

    def get_history(self, user_id: str) -> list[dict]:
        self._cleanup_expired()
        return self._sessions[user_id]["history"]

    def add_turn(self, user_id: str, user_text: str, bot_reply: str) -> None:
        """Tambah satu pasang turn (user + model) ke history."""
        session = self._sessions[user_id]
        session["last_active"] = datetime.now()

        # Potong teks panjang agar context tidak overflow
        u_text = user_text[:MAX_MSG_CHARS]
        b_text = bot_reply[:MAX_MSG_CHARS]

        session["history"].append({"role": "user",  "parts": [{"text": u_text}]})
        session["history"].append({"role": "model", "parts": [{"text": b_text}]})

        # Keep only last MAX_HISTORY pairs (= MAX_HISTORY*2 messages)
        if len(session["history"]) > MAX_HISTORY * 2:
            session["history"] = session["history"][-(MAX_HISTORY * 2):]

    def clear(self, user_id: str) -> None:
        """Reset conversation session user."""
        if user_id in self._sessions:
            self._sessions[user_id]["history"] = []
            self._sessions[user_id]["last_active"] = datetime.now()
            logger.info(f"[conv] session cleared: {user_id}")

    def session_info(self, user_id: str) -> dict:
        s = self._sessions.get(user_id, {})
        turns = len(s.get("history", [])) // 2
        last  = s.get("last_active")
        idle  = int((datetime.now() - last).total_seconds() / 60) if last else 0
        return {"turns": turns, "idle_minutes": idle}
