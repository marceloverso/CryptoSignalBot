# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — utils.py
#  Funciones de utilidad: tiempo, texto, hashes, chunks.
# ═══════════════════════════════════════════════════════════════

import hashlib, unicodedata, logging
from datetime import datetime, timezone, timedelta
from html import escape

logger = logging.getLogger(__name__)
MAX_TELEGRAM_LEN = 3900


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)

def ahora_colombia() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=5)

def ts_colombia(ts_ms: int) -> str:
    """Convierte timestamp Binance (ms) a hora Colombia HH:MM."""
    return (datetime.utcfromtimestamp(ts_ms / 1000)
            - timedelta(hours=5)).strftime("%H:%M")

def fecha_colombia() -> str:
    return ahora_colombia().strftime("%Y-%m-%d")

def safe_html(value) -> str:
    return escape("" if value is None else str(value), quote=True)

def _chunk_text(text: str, max_len: int = MAX_TELEGRAM_LEN) -> list:
    if len(text) <= max_len:
        return [text]
    chunks, current = [], ""
    for line in text.splitlines(True):
        if len(line) > max_len:
            if current: chunks.append(current); current = ""
            for i in range(0, len(line), max_len):
                chunks.append(line[i:i+max_len])
            continue
        if len(current) + len(line) > max_len and current:
            chunks.append(current); current = ""
        current += line
    if current: chunks.append(current)
    return chunks

def build_signal_id(symbol: str, direccion: str, timeframe: str,
                    timestamp_ms: int) -> str:
    raw = f"{symbol}|{direccion}|{timeframe}|{timestamp_ms}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]

def fmt_precio(precio: float, symbol: str = "") -> str:
    """Formatea precio según el activo."""
    if "BTC" in symbol: return f"${precio:,.2f}"
    if precio > 100:    return f"${precio:,.2f}"
    return f"${precio:.4f}"

def fmt_pct(valor: float) -> str:
    signo = "+" if valor >= 0 else ""
    return f"{signo}{valor:.2f}%"

def fmt_cop(valor: int) -> str:
    signo = "+" if valor >= 0 else ""
    return f"{signo}${abs(valor):,}"
