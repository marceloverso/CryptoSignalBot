# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — gemini_ai.py
#  Análisis de contexto por trade usando Gemini 2.0 Flash.
# ═══════════════════════════════════════════════════════════════

import logging
from config import GEMINI_API_KEY, GEMINI_URL, SESION, CAPITAL
from utils  import ahora_colombia

logger = logging.getLogger(__name__)


def _llamar_gemini(prompt: str, max_tokens: int = 200) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        r = SESION.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature":     0.3,
                },
            },
            timeout=25,
        )
        if r.ok:
            return (
                r.json()
                .get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
        logger.warning(f"⚠️ Gemini {r.status_code}: {r.text[:120]}")
    except Exception as e:
        logger.warning(f"⚠️ Gemini: {type(e).__name__}: {e}")
    return None


def analizar_trade_gemini(
    nombre: str,
    direccion: str,
    score: int,
    precio: float,
    razones: list[str],
    metricas: dict,
) -> str:
    """
    Genera 2 oraciones de contexto para la alerta de trading.
    Busca en Google noticias recientes del activo.
    """
    if not GEMINI_API_KEY:
        return ""

    razon_txt = " | ".join(razones[:4]) if razones else "indicadores técnicos"
    rsi_val   = metricas.get("rsi", "?")
    vol_val   = metricas.get("vol_ratio", "?")

    prompt = (
        f"Busca noticias y contexto actual sobre {nombre} en el mercado crypto/forex.\n"
        f"El análisis técnico dice: {direccion} | Score {score}/100 | "
        f"RSI {rsi_val} | Volumen x{vol_val} promedio | Precio ${precio:,.4f}\n"
        f"Factores técnicos: {razon_txt}\n\n"
        f"Responde en español con EXACTAMENTE 2 oraciones cortas y directas:\n"
        f"1. Contexto fundamental actual (noticias, eventos, sentimiento del mercado)\n"
        f"2. ¿Confirma o contradice la señal {direccion}?\n"
        f"Sin markdown, sin asteriscos, máximo 40 palabras total."
    )

    resultado = _llamar_gemini(prompt, max_tokens=120)
    return resultado if resultado else ""


def analisis_diario_gemini(historial: dict) -> bool:
    """Resumen nocturno de la jornada de trading."""
    if not GEMINI_API_KEY:
        logger.info("🤖 Análisis Gemini: GEMINI_API_KEY no configurado")
        return False

    from telegram_bot import enviar_telegram

    try:
        hoy    = ahora_colombia().strftime("%Y-%m-%d")
        trades_hoy = [
            t for t in historial.get("trades", [])
            if t.get("fecha") == hoy
        ]
        if not trades_hoy:
            logger.info("🤖 Sin trades hoy")
            return False

        resueltos  = [t for t in trades_hoy if t.get("estado") != "pendiente"]
        ganados    = [t for t in resueltos   if t.get("estado") == "ganada"]
        perdidos   = [t for t in resueltos   if t.get("estado") == "perdida"]
        pendientes = [t for t in trades_hoy  if t.get("estado") == "pendiente"]
        gan_neta   = sum(t.get("ganancia_real",0) for t in resueltos)
        wr_hoy     = round(len(ganados)/len(resueltos)*100,1) if resueltos else 0

        todos_res  = [t for t in historial["trades"] if t.get("estado") != "pendiente"]
        total_w    = sum(1 for t in todos_res if t["estado"] == "ganada")
        wr_total   = round(total_w/len(todos_res)*100,1) if todos_res else 0
        balance    = CAPITAL + sum(t.get("ganancia_real",0) for t in todos_res)

        def linea(t):
            r = t.get("precio_cierre","?")
            return (
                f"  - {t['nombre']} {t['direccion']} "
                f"entry:{t['precio_entrada']} "
                f"→ {t.get('estado','?').upper()} "
                f"${t.get('ganancia_real',0):,}"
            )

        detalle = "\n".join(linea(t) for t in trades_hoy)

        prompt = (
            f"Eres el asistente de trading algorítmico. Hoy es {hoy}.\n"
            f"Escribe un mensaje DIRECTO para Telegram (máximo 200 palabras).\n"
            f"Sin markdown, sin asteriscos. Usa emojis.\n\n"
            f"TRADES DE HOY:\n{detalle}\n\n"
            f"RESUMEN HOY: {len(ganados)}W / {len(perdidos)}L / "
            f"{len(pendientes)} pendientes | WR {wr_hoy}% | neto ${gan_neta:,} COP\n"
            f"ACUMULADO: {total_w}/{len(todos_res)} ({wr_total}% WR) | "
            f"Balance ${balance:,} COP (inicial ${CAPITAL:,})\n\n"
            f"1. Saluda con emoji según rendimiento\n"
            f"2. Comenta brevemente qué activos funcionaron\n"
            f"3. Una recomendación concreta para mañana\n"
            f"4. Cierra con frase motivadora breve"
        )

        analisis = _llamar_gemini(prompt, max_tokens=350)
        if not analisis:
            return False

        sep = "─" * 28
        msg = (
            f"🤖 <b>RESUMEN TRADING — {hoy}</b>\n"
            f"{sep}\n\n{analisis}\n\n{sep}\n"
            f"<i>Análisis por Gemini AI</i>"
        )
        enviar_telegram(msg)
        logger.info("✅ Análisis diario Gemini enviado")
        return True

    except Exception as e:
        logger.error(f"❌ analisis_diario_gemini: {e}")
        return False
