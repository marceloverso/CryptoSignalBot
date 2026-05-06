# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — market_data.py
#  Comunicación con Binance API:
#  - Velas OHLCV (candlestick data)
#  - Precio actual
#  - Variación 24h
#  - Volumen
#  Equivalente a fetcher.py del bot de apuestas.
# ═══════════════════════════════════════════════════════════════

import logging
from config import BINANCE_API_KEY, BINANCE_BASE, SESION

logger = logging.getLogger(__name__)

# Cuántas velas pedir — suficiente para todos los indicadores
VELAS_LIMIT = 100


def get_velas(symbol: str, interval: str = "1h") -> list[dict] | None:
    """
    Descarga las últimas VELAS_LIMIT velas de Binance.
    Retorna lista de dicts con: open, high, low, close, volume, timestamp.
    Retorna None si falla.

    interval: "1h", "4h", "1d", "15m", etc.
    """
    try:
        r = SESION.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={
                "symbol":   symbol,
                "interval": interval,
                "limit":    VELAS_LIMIT,
            },
            headers={"X-MBX-APIKEY": BINANCE_API_KEY},
            timeout=15,
        )
        if not r.ok:
            logger.warning(f"⚠️ Binance klines {symbol}/{interval}: {r.status_code}")
            return None

        velas = []
        for k in r.json():
            velas.append({
                "timestamp": int(k[0]),
                "open":      float(k[1]),
                "high":      float(k[2]),
                "low":       float(k[3]),
                "close":     float(k[4]),
                "volume":    float(k[5]),
            })
        return velas

    except Exception as e:
        logger.warning(f"⚠️ get_velas {symbol}/{interval}: {type(e).__name__}: {e}")
        return None


def get_ticker_24h(symbol: str) -> dict | None:
    """
    Obtiene datos de las últimas 24 horas: precio, cambio%, volumen.
    """
    try:
        r = SESION.get(
            f"{BINANCE_BASE}/api/v3/ticker/24hr",
            params={"symbol": symbol},
            headers={"X-MBX-APIKEY": BINANCE_API_KEY},
            timeout=10,
        )
        if not r.ok:
            return None
        d = r.json()
        return {
            "precio_actual":  float(d["lastPrice"]),
            "cambio_pct_24h": float(d["priceChangePercent"]),
            "volumen_24h":    float(d["volume"]),
            "precio_max_24h": float(d["highPrice"]),
            "precio_min_24h": float(d["lowPrice"]),
        }
    except Exception as e:
        logger.warning(f"⚠️ get_ticker_24h {symbol}: {e}")
        return None


def get_datos_completos(symbol: str) -> dict | None:
    """
    Descarga velas 1h + 4h + ticker 24h para un símbolo.
    Retorna dict con todo lo necesario para indicators.py.
    Retorna None si falla la descarga principal.
    """
    velas_1h = get_velas(symbol, "1h")
    if not velas_1h:
        logger.warning(f"⚠️ Sin datos 1h para {symbol}")
        return None

    velas_4h  = get_velas(symbol, "4h")
    ticker    = get_ticker_24h(symbol)

    logger.info(
        f"📡 {symbol}: {len(velas_1h)} velas 1h | "
        f"{len(velas_4h) if velas_4h else 0} velas 4h | "
        f"precio: {ticker['precio_actual'] if ticker else '?'}"
    )

    return {
        "symbol":   symbol,
        "velas_1h": velas_1h,
        "velas_4h": velas_4h or [],
        "ticker":   ticker or {},
        "precio":   velas_1h[-1]["close"],   # último precio de cierre
    }
