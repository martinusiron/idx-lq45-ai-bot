"""
tests/test_sprint1.py — Unit tests untuk Sprint 1 features:
  - ConversationStore
  - PriceAlertManager
  - chart_vision helpers
"""
from __future__ import annotations
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


class TestConversationStore(unittest.TestCase):

    def setUp(self):
        from conversation_store import ConversationStore
        self.cs = ConversationStore()

    def test_empty_history_initially(self):
        history = self.cs.get_history("user_abc")
        self.assertEqual(history, [])

    def test_add_turn_creates_two_messages(self):
        self.cs.add_turn("user_abc", "hello", "hi there")
        history = self.cs.get_history("user_abc")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "model")

    def test_add_multiple_turns(self):
        for i in range(5):
            self.cs.add_turn("user_abc", f"msg {i}", f"reply {i}")
        history = self.cs.get_history("user_abc")
        self.assertEqual(len(history), 10)

    def test_max_history_trimming(self):
        from conversation_store import MAX_HISTORY
        # Add more than MAX_HISTORY turns
        for i in range(MAX_HISTORY + 3):
            self.cs.add_turn("user_abc", f"msg {i}", f"reply {i}")
        history = self.cs.get_history("user_abc")
        # Should be trimmed to MAX_HISTORY * 2
        self.assertLessEqual(len(history), MAX_HISTORY * 2)

    def test_clear_resets_history(self):
        self.cs.add_turn("user_abc", "hello", "hi")
        self.cs.clear("user_abc")
        history = self.cs.get_history("user_abc")
        self.assertEqual(history, [])

    def test_clear_nonexistent_user(self):
        # Should not raise
        self.cs.clear("nonexistent_user")

    def test_separate_sessions_per_user(self):
        self.cs.add_turn("user_1", "msg1", "reply1")
        self.cs.add_turn("user_2", "msg2", "reply2")
        self.assertEqual(len(self.cs.get_history("user_1")), 2)
        self.assertEqual(len(self.cs.get_history("user_2")), 2)

    def test_long_message_truncated(self):
        from conversation_store import MAX_MSG_CHARS
        long_msg = "A" * (MAX_MSG_CHARS + 500)
        self.cs.add_turn("user_abc", long_msg, "ok")
        history = self.cs.get_history("user_abc")
        user_text = history[0]["parts"][0]["text"]
        self.assertLessEqual(len(user_text), MAX_MSG_CHARS)

    def test_session_info(self):
        self.cs.add_turn("user_abc", "hi", "hello")
        info = self.cs.session_info("user_abc")
        self.assertEqual(info["turns"], 1)
        self.assertGreaterEqual(info["idle_minutes"], 0)

    def test_session_ttl_expiry(self):
        from conversation_store import ConversationStore, SESSION_TTL
        from datetime import datetime, timedelta
        cs = ConversationStore()
        cs.add_turn("user_expire", "hi", "hello")
        # Manually set last_active to expired
        cs._sessions["user_expire"]["last_active"] = (
            datetime.now() - timedelta(minutes=SESSION_TTL + 1)
        )
        # Trigger cleanup via get_history
        cs.get_history("new_user")  # triggers cleanup
        # Expired session should be gone
        self.assertNotIn("user_expire", cs._sessions)

    def test_history_format_gemini_compatible(self):
        """Pastikan format sesuai Gemini multi-turn API."""
        self.cs.add_turn("user_abc", "analisa BBCA", "BBCA lagi bullish...")
        history = self.cs.get_history("user_abc")
        for msg in history:
            self.assertIn("role", msg)
            self.assertIn("parts", msg)
            self.assertIsInstance(msg["parts"], list)
            self.assertIn("text", msg["parts"][0])
            self.assertIn(msg["role"], ["user", "model"])


class TestPriceAlertManager(unittest.TestCase):

    def setUp(self):
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        from price_alert import PriceAlertManager
        self.mgr = PriceAlertManager(mock_app)

    def test_add_alert_success(self):
        ok = self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
        self.assertTrue(ok)

    def test_get_alerts_empty(self):
        alerts = self.mgr.get_alerts("user_new")
        self.assertEqual(alerts, [])

    def test_add_and_get_alert(self):
        self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
        alerts = self.mgr.get_alerts("user1")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["symbol"], "BBCA")
        self.assertEqual(alerts[0]["target"], 9200)
        self.assertEqual(alerts[0]["direction"], "atas")

    def test_max_5_alerts(self):
        syms = ["BBCA", "BBRI", "TLKM", "BMRI", "ASII"]
        for s in syms:
            ok = self.mgr.add_alert("user1", "chat1", s, 5000, "atas")
            self.assertTrue(ok)
        # 6th should fail
        ok = self.mgr.add_alert("user1", "chat1", "GOTO", 100, "atas")
        self.assertFalse(ok)

    def test_remove_alert(self):
        self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
        n = self.mgr.remove_alert("user1", "BBCA")
        self.assertEqual(n, 1)
        self.assertEqual(self.mgr.get_alerts("user1"), [])

    def test_remove_nonexistent_alert(self):
        n = self.mgr.remove_alert("user1", "NONEXISTENT")
        self.assertEqual(n, 0)

    def test_duplicate_direction_replaced(self):
        """Alert dengan symbol+direction sama harus replace yang lama."""
        self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
        self.mgr.add_alert("user1", "chat1", "BBCA", 9500, "atas")  # same direction
        alerts = self.mgr.get_alerts("user1")
        bbca_atas = [a for a in alerts if a["symbol"] == "BBCA" and a["direction"] == "atas"]
        self.assertEqual(len(bbca_atas), 1)
        self.assertEqual(bbca_atas[0]["target"], 9500)  # updated

    def test_both_directions_coexist(self):
        """Alert atas dan bawah untuk saham sama boleh coexist."""
        self.mgr.add_alert("user1", "chat1", "BBCA", 9500, "atas")
        self.mgr.add_alert("user1", "chat1", "BBCA", 8500, "bawah")
        alerts = self.mgr.get_alerts("user1")
        bbca = [a for a in alerts if a["symbol"] == "BBCA"]
        self.assertEqual(len(bbca), 2)

    def test_get_all_active(self):
        self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
        self.mgr.add_alert("user2", "chat2", "TLKM", 3500, "bawah")
        active = self.mgr.get_all_active()
        self.assertEqual(len(active), 2)
        symbols = {a["symbol"] for a in active}
        self.assertIn("BBCA", symbols)
        self.assertIn("TLKM", symbols)

    def test_triggered_alert_removed(self):
        async def run():
            self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
            # Mock price fetch to return value above target
            with patch.object(self.mgr, '_fetch_price', return_value=9300.0):
                await self.mgr.check_all()
            # Alert should be removed after trigger
            alerts = self.mgr.get_alerts("user1")
            self.assertEqual(len(alerts), 0)
        asyncio.run(run())

    def test_not_triggered_alert_stays(self):
        async def run():
            self.mgr.add_alert("user1", "chat1", "BBCA", 9200, "atas")
            # Price below target — should not trigger
            with patch.object(self.mgr, '_fetch_price', return_value=9100.0):
                await self.mgr.check_all()
            alerts = self.mgr.get_alerts("user1")
            self.assertEqual(len(alerts), 1)  # still there
        asyncio.run(run())

    def test_bawah_direction_trigger(self):
        async def run():
            self.mgr.add_alert("user1", "chat1", "BBRI", 4800, "bawah")
            # Price below target — should trigger
            with patch.object(self.mgr, '_fetch_price', return_value=4750.0):
                await self.mgr.check_all()
            alerts = self.mgr.get_alerts("user1")
            self.assertEqual(len(alerts), 0)
        asyncio.run(run())


class TestChartVision(unittest.TestCase):

    def test_analyze_chart_timeout(self):
        """Test timeout handling."""
        async def run():
            mock_model = MagicMock()
            mock_model.generate_content.side_effect = asyncio.TimeoutError()

            from chart_vision import analyze_chart_image
            # Create a minimal valid PNG bytes
            import struct, zlib
            def make_minimal_png():
                sig = b'\x89PNG\r\n\x1a\n'
                def chunk(t, d):
                    c = struct.pack('>I', len(d)) + t + d
                    return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
                ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
                idat = chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff'))
                iend = chunk(b'IEND', b'')
                return sig + ihdr + idat + iend

            result = await analyze_chart_image(mock_model, make_minimal_png())
            self.assertIn("timeout", result.lower())
        asyncio.run(run())

    def test_system_prompt_contains_key_concepts(self):
        from chart_vision import CHART_SYSTEM_PROMPT
        required = ["support", "resistance", "trend", "RSI", "MACD", "volume", "entry", "SL", "TP"]
        for concept in required:
            self.assertIn(concept, CHART_SYSTEM_PROMPT, f"'{concept}' hilang dari CHART_SYSTEM_PROMPT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
