"""
chart_vision.py — Analisa chart screenshot menggunakan Gemini Vision.
User kirim foto/screenshot chart → Gemini analisa pattern & level.
"""
from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from google import genai
from google.genai import types as genai_types
from PIL import Image

logger = logging.getLogger(__name__)

CHART_SYSTEM_PROMPT = """Kamu adalah DUKUN KEUANGAN — analis teknikal expert untuk IDX (BEI).
User mengirim screenshot chart saham. Analisa secara mendalam:

1. IDENTIFIKASI CHART:
   - Timeframe (jika terlihat)
   - Saham/ticker (jika terlihat)
   - Periode waktu

2. TREND & STRUKTUR:
   - Trend utama: uptrend/downtrend/sideways
   - Higher High/Higher Low atau Lower High/Lower Low
   - Struktur pasar: accumulation/distribution/markup/markdown

3. LEVEL KRITIS:
   - Support kuat (sebutkan harga spesifik jika terlihat)
   - Resistance kuat (sebutkan harga spesifik jika terlihat)
   - Area demand & supply zone

4. INDIKATOR (jika terlihat di chart):
   - Moving Average: posisi harga vs MA, golden/death cross
   - RSI/Stochastic: overbought/oversold/divergence
   - MACD: crossover, histogram, divergence
   - Volume: spike, climax, dry up
   - Bollinger Bands: squeeze, expansion, touch band

5. POLA CANDLESTICK/CHART:
   - Pola reversal: Hammer, Shooting Star, Engulfing, Doji, Morning/Evening Star
   - Pola continuation: Flag, Pennant, Triangle, Cup & Handle
   - Pola besar: Head & Shoulders, Double Top/Bottom

6. SKENARIO TRADING:
   - Setup BULLISH (jika ada): entry zone, TP1, TP2, SL, RRR
   - Setup BEARISH (jika ada): entry zone, TP1, TP2, SL, RRR
   - Konfirmasi yang dibutuhkan sebelum entry

7. KESIMPULAN:
   - Bias saat ini: BULLISH / BEARISH / NEUTRAL
   - Level yang paling kritis untuk diperhatikan
   - Rekomendasi: WAIT / WATCH / READY TO ENTER

Format: padat, terstruktur, gunakan bullet points.
DYOR — keputusan ada di tanganmu."""


async def analyze_chart_image(
    model,
    image_bytes: bytes,
    additional_context: str = "",
) -> str:
    """
    Analisa chart image menggunakan Gemini Vision.
    Returns: string analisa dari Gemini
    """
    try:
        # Convert bytes ke PIL Image
        img = Image.open(BytesIO(image_bytes))

        prompt = CHART_SYSTEM_PROMPT
        if additional_context:
            prompt += f"\n\nKonteks tambahan dari user: {additional_context}"

        # Gemini vision: kirim image + text
        import io
        img_bytes_io = io.BytesIO()
        img.save(img_bytes_io, format="JPEG")
        img_bytes_io.seek(0)
        
        response = await asyncio.wait_for(
            asyncio.to_thread(
                model.models.generate_content,
                model="gemini-2.5-flash-lite",
                contents=[
                    genai_types.Part.from_bytes(
                        data=img_bytes_io.read(),
                        mime_type="image/jpeg"
                    ),
                    prompt,
                ],
                config=genai_types.GenerateContentConfig(
                    http_options=genai_types.HttpOptions(timeout=90000)
                )
            ),
            timeout=95.0,
        )
        return response.text.strip()

    except asyncio.TimeoutError:
        return "⚠️ Analisa chart timeout. Coba kirim ulang gambar."
    except Exception as exc:
        logger.error(f"[chart_vision] error: {exc}")
        return f"⚠️ Gagal analisa chart: {exc}"
