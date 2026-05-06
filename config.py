# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — config.py
# ═══════════════════════════════════════════════════════════════

import os, sys, logging, requests
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

def _env_int(name, default):
    raw = os.environ.get(name)
    if not raw or not str(raw).strip(): return int(default)
    try: return int(str(raw).strip())
    except ValueError: return int(default)

def _env_float(name, default):
    raw = os.environ.get(name)
    if not raw: return float(default)
    try: return float(str(raw).strip())
    except ValueError: return float(default)

def _env_str(name, default=""):
    return os.environ.get(name, default).strip()

def validar_configuracion():
    faltantes = [v for v in ["BOT_TOKEN","CHAT_ID","BINANCE_API_KEY"] if not os.environ.get(v)]
    if faltantes:
        logger.critical(f"❌ Faltan secrets: {', '.join(faltantes)}")
        sys.exit(1)
    logger.info("✅ Configuración validada")

# Secrets
BOT_TOKEN        = _env_str("BOT_TOKEN")
CHAT_ID          = _env_str("CHAT_ID")
BINANCE_API_KEY  = _env_str("BINANCE_API_KEY")
BINANCE_SECRET   = _env_str("BINANCE_SECRET_KEY")
GEMINI_API_KEY   = _env_str("GEMINI_API_KEY")
GSHEETS_CREDS    = _env_str("GOOGLE_SERVICE_ACCOUNT_JSON")
GSHEETS_SHEET_ID = _env_str("GOOGLE_SHEET_ID")

# Parámetros operativos
CAPITAL      = _env_int("CAPITAL",     300_000)
SCORE_MINIMO = _env_int("SCORE_MINIMO", 75)
STAKE_PCT    = _env_float("STAKE_PCT",  0.02)

# Martingala
MART_FACTOR    = 1.5
MART_MAX_NIVEL = 6

def calcular_stake(nivel: int) -> int:
    nivel = max(1, min(nivel, MART_MAX_NIVEL))
    return round(CAPITAL * STAKE_PCT * (MART_FACTOR ** (nivel - 1)))

STAKE_BASE = calcular_stake(1)

# Risk/Reward
TP_MULTIPLIER = 1.5
SL_MULTIPLIER = 1.0

# Activos
PARES = [
    {"symbol": "BTCUSDT", "nombre": "BTC/USDT", "tipo": "crypto", "emoji": "₿"},
    {"symbol": "ETHUSDT", "nombre": "ETH/USDT", "tipo": "crypto", "emoji": "Ξ"},
    {"symbol": "SOLUSDT", "nombre": "SOL/USDT", "tipo": "crypto", "emoji": "◎"},
    {"symbol": "BNBUSDT", "nombre": "BNB/USDT", "tipo": "crypto", "emoji": "🔶"},
    {"symbol": "XRPUSDT", "nombre": "XRP/USDT", "tipo": "crypto", "emoji": "✕"},
    {"symbol": "ADAUSDT", "nombre": "ADA/USDT", "tipo": "crypto", "emoji": "₳"},
]

TIMEFRAMES = ["1h", "4h"]

# URLs
BINANCE_BASE = "https://api.binance.com"
GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

# Persistencia
DATA_DIR    = Path("./bot_data")
HISTORIAL_F = DATA_DIR / "historial.json"
DATA_DIR.mkdir(exist_ok=True)

# Sesión HTTP
def crear_sesion():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=2,
        status_forcelist=[429,500,502,503,504],
        allowed_methods=["GET","POST"])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://",  HTTPAdapter(max_retries=retries))
    return s

SESION = crear_sesion()
MAX_TELEGRAM_LEN = 3900
