# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — telegram_bot.py
#  Envío y formateo de alertas de trading.
# ═══════════════════════════════════════════════════════════════

import logging
from config import BOT_TOKEN, CHAT_ID, SESION, MART_MAX_NIVEL, calcular_stake
from utils  import safe_html, _chunk_text, fmt_precio, fmt_pct, fmt_cop

logger = logging.getLogger(__name__)

def enviar_telegram(msg: str) -> bool:
    try:
        for chunk in _chunk_text(msg):
            r = SESION.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id":CHAT_ID, "text":chunk, "parse_mode":"HTML"},
                timeout=10,
            )
            if not r.ok:
                logger.error(f"⚠️ Telegram {r.status_code}: {r.text[:100]}")
                return False
        return True
    except Exception as e:
        logger.error(f"⚠️ enviar_telegram: {e}")
        return False


def formatear_alerta_trade(
    nombre: str,
    emoji_par: str,
    direccion: str,
    score: int,
    precio_entrada: float,
    tp: float,
    sl: float,
    timeframe: str,
    razones: list[str],
    metricas: dict,
    nivel_mart: int,
    mart_activa: bool,
    gemini_txt: str = "",
    ticker: dict = None,
) -> str:
    """Formatea la alerta de trading para Telegram."""
    try:
        stake       = calcular_stake(nivel_mart)
        es_long     = (direccion == "LONG")
        dir_emoji   = "🟢" if es_long else "🔴"
        dir_label   = "LONG  📈" if es_long else "SHORT 📉"
        barra       = "█" * round(score/10) + "░" * (10 - round(score/10))

        # Variación 24h
        cambio_24h = ticker.get("cambio_pct_24h", 0) if ticker else 0
        cambio_txt = fmt_pct(cambio_24h)
        cambio_dir = "📈" if cambio_24h >= 0 else "📉"

        # TP/SL en %
        if es_long:
            tp_pct = round((tp - precio_entrada) / precio_entrada * 100, 2)
            sl_pct = round((sl - precio_entrada) / precio_entrada * 100, 2)
        else:
            tp_pct = round((precio_entrada - tp) / precio_entrada * 100, 2)
            sl_pct = round((precio_entrada - sl) / precio_entrada * 100, 2)

        rr = round(abs(tp_pct / sl_pct), 2) if sl_pct else 0
        gan_pot   = round(stake * abs(tp_pct/100))
        perd_max  = round(stake * abs(sl_pct/100))

        # Métricas clave
        rsi_txt  = f"RSI: {metricas.get('rsi','?')}" if metricas.get('rsi') else ""
        vol_txt  = f"Vol: x{metricas.get('vol_ratio','?')}p.a." if metricas.get('vol_ratio') else ""

        razones_txt = "\n".join(f"  · {safe_html(r)}" for r in razones[:5])

        # Martingala
        if not mart_activa:
            mart_txt = f"\n🛑 <b>MARTINGALA DETENIDA</b>\n"
        elif nivel_mart == 1:
            mart_txt = f"\n🎯 <b>Trade 1/{MART_MAX_NIVEL}</b> — inicio de ciclo\n"
        else:
            mart_txt = f"\n⚠️ <b>Trade {nivel_mart}/{MART_MAX_NIVEL}</b> — Martingala activa\n"

        gemini_block = f"\n🤖 <i>{safe_html(gemini_txt)}</i>\n" if gemini_txt else ""

        return (
            f"{dir_emoji} <b>SEÑAL {dir_label}</b>\n\n"
            f"{emoji_par} <b>{safe_html(nombre)}</b>  "
            f"{cambio_dir} {safe_html(cambio_txt)} (24h)\n"
            f"💲 Precio: <b>{fmt_precio(precio_entrada, nombre)}</b>\n\n"
            f"📊 <b>Score: {score}/100</b> | {safe_html(timeframe)}\n"
            f"<code>{barra}</code>\n\n"
            f"🎯 <b>Take Profit:</b> {fmt_precio(tp, nombre)} "
            f"(+{tp_pct}%)\n"
            f"🛑 <b>Stop Loss:</b>   {fmt_precio(sl, nombre)} "
            f"(-{abs(sl_pct)}%)\n"
            f"⚖️ <b>R/R Ratio:</b>   1:{rr}\n\n"
            f"📈 Indicadores: {safe_html(rsi_txt)}  {safe_html(vol_txt)}\n\n"
            f"<b>Razones del score:</b>\n{razones_txt}\n"
            f"{mart_txt}"
            f"💵 <b>Stake: ${stake:,} COP</b>\n"
            f"✅ Ganancia potencial: {fmt_cop(gan_pot)} COP\n"
            f"❌ Pérdida máxima:    {fmt_cop(-perd_max)} COP\n"
            f"{gemini_block}"
            f"\n⚠️ No es consejo financiero • DYOR"
        )
    except Exception as e:
        logger.error(f"❌ formatear_alerta_trade: {e}")
        return ""


def formatear_stop_martingala(balance: int) -> str:
    from config import CAPITAL
    return (
        f"🛑 <b>STOP — MARTINGALA AGOTADA</b>\n\n"
        f"<b>{MART_MAX_NIVEL} trades consecutivos perdidos.</b>\n\n"
        f"El bot sigue analizando y enviando señales\n"
        f"pero el stake dirá STOP hasta que ganes.\n\n"
        f"💰 Balance actual: <b>${balance:,} COP</b>\n"
        f"(Capital inicial: ${CAPITAL:,} COP)\n\n"
        f"🔄 Se reactiva automáticamente con la próxima ganancia.\n"
        f"⚠️ <i>Revisá tu estrategia antes de continuar.</i>"
    )


def formatear_stats(stats: dict | None) -> str:
    if not stats:
        return "📊 Sin trades resueltos aún."

    gan = stats["gan_neta"]
    dd  = stats["max_dd"]

    lines = [
        "📊 <b>ESTADÍSTICAS ACUMULADAS</b>\n",
        f"🎯 Resueltos: {stats['total']} | ⏳ Pendientes: {stats['pendientes']}",
        f"💰 Ganancia neta: {fmt_cop(gan)} COP",
        f"📈 WR: {stats['wr']}% | ROI: {stats['roi']}%",
        f"💼 Balance: ${stats['balance']:,} (pico: ${stats['pico']:,})\n",
        "📊 <b>Win rate por score:</b>",
    ]
    for rango, key in [("70-79","score_70_79"),("80-89","score_80_89"),("90+","score_90")]:
        s = stats.get(key)
        if s:
            lines.append(f"  Score {rango}: {s['ganadas']}/{s['total']} ({s['wr']}% | ROI {s['roi']}%)")

    lines += [
        f"\n🔁 Racha perdedora máx: {stats['racha_l_max']} | ganadora máx: {stats['racha_w_max']}",
        f"📉 Drawdown máx: ${dd:,} ({stats['max_dd_pct']}%)",
    ]
    if stats["dd_actual"] > 0:
        lines.append(f"  ⚠️ Drawdown actual: ${stats['dd_actual']:,} bajo el pico")

    return "\n".join(lines)
