# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — main.py
#  Orquestador principal.
#
#  FLUJO POR RUN (cada hora):
#  1. Verificar resultados pendientes (TP/SL alcanzado)
#  2. Actualizar martingala
#  3. Para cada par en PARES:
#     a. Descargar datos de mercado (Binance)
#     b. Calcular score LONG y SHORT
#     c. Si score >= SCORE_MINIMO → enviar alerta
#  4. Si es medianoche Colombia → resumen Gemini + backup
# ═══════════════════════════════════════════════════════════════

import sys, time, logging
from config import (
    validar_configuracion, PARES, SCORE_MINIMO,
    CAPITAL,
)
from utils        import ahora_colombia, safe_html, fecha_colombia
from market_data  import get_datos_completos
from indicators   import calcular_score, calcular_tp_sl
from historial    import (
    cargar_historial, guardar_historial, registrar_trade,
    verificar_resultados, actualizar_martingala,
    necesita_stop_alert, marcar_stop_notificado,
    calcular_stats,
)
from telegram_bot import (
    enviar_telegram, formatear_alerta_trade,
    formatear_stop_martingala, formatear_stats,
)
from sheets    import sincronizar_sheets
from gemini_ai import analizar_trade_gemini, analisis_diario_gemini
from backup    import backup_historial_github

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def es_bloque_cierre() -> bool:
    """True a medianoche Colombia (23h-01h) — resumen + backup."""
    hora = ahora_colombia().hour
    return hora in (23, 0)


def main():
    try:
        validar_configuracion()
        ahora    = ahora_colombia().strftime("%Y-%m-%d %H:%M")
        logger.info(f"🤖 TradeBot v1.0 — {ahora} Colombia")

        # ── Cargar historial ──────────────────────────────────
        historial    = cargar_historial()
        existing_ids = {t.get("id") for t in historial.get("trades", [])}

        # ── Verificar resultados pendientes ───────────────────
        actualizados = verificar_resultados(historial)
        if actualizados > 0:
            guardar_historial(historial)
            logger.info(f"📊 {actualizados} trade(s) resuelto(s)")
            sincronizar_sheets(historial)

        # ── Actualizar martingala ─────────────────────────────
        if actualizar_martingala(historial):
            guardar_historial(historial)

        # ── STOP alert ────────────────────────────────────────
        if necesita_stop_alert(historial):
            balance = CAPITAL + sum(
                t.get("ganancia_real",0) for t in historial["trades"]
                if t.get("estado") != "pendiente"
            )
            enviar_telegram(formatear_stop_martingala(balance))
            marcar_stop_notificado(historial)
            guardar_historial(historial)

        # ── Estado martingala ─────────────────────────────────
        mart       = historial["martingala"]
        nivel_mart = mart["nivel"]
        mart_activa= mart["activa"]
        logger.info(
            f"🎯 Martingala: nivel {nivel_mart}/6 | "
            f"racha:{mart['racha_perdidas']} | activa:{mart_activa}"
        )

        # ── Analizar cada par ─────────────────────────────────
        alertas_enviadas = 0
        log_trades: list = []
        stats = calcular_stats(historial)
        stats_txt = formatear_stats(stats)

        for par in PARES:
            symbol = par["symbol"]
            nombre = par["nombre"]
            emoji  = par["emoji"]

            logger.info(f"🔍 Analizando {nombre}...")
            datos = get_datos_completos(symbol)
            if not datos:
                logger.warning(f"⚠️ Sin datos para {nombre}")
                continue

            precio = datos["precio"]
            ticker = datos.get("ticker", {})

            # Evaluar LONG y SHORT — alertar el mejor si supera el umbral
            for direccion in ["LONG", "SHORT"]:
                score, razones, rechazos, metricas = calcular_score(
                    datos, direccion=direccion
                )

                logger.info(
                    f"  {nombre} {direccion}: score={score} | "
                    f"rechazos={rechazos}"
                )

                if rechazos or score < SCORE_MINIMO:
                    continue

                # Calcular TP/SL
                atr = metricas.get("atr")
                tp, sl = calcular_tp_sl(precio, atr, direccion)

                # ID único para dedup
                from utils import build_signal_id
                import time as time_mod
                ts = int(ahora_colombia().timestamp() * 1000)
                sid = build_signal_id(symbol, direccion, "1h", ts // (3600*1000))

                if sid in existing_ids:
                    logger.info(f"↩️ Duplicado: {nombre} {direccion}")
                    continue

                # Análisis Gemini
                gemini_txt = analizar_trade_gemini(
                    nombre, direccion, score, precio, razones, metricas
                )

                # Formatear y enviar
                msg = formatear_alerta_trade(
                    nombre         = nombre,
                    emoji_par      = emoji,
                    direccion      = direccion,
                    score          = score,
                    precio_entrada = precio,
                    tp             = tp,
                    sl             = sl,
                    timeframe      = "1H/4H",
                    razones        = razones,
                    metricas       = metricas,
                    nivel_mart     = nivel_mart,
                    mart_activa    = mart_activa,
                    gemini_txt     = gemini_txt,
                    ticker         = ticker,
                )

                if not msg:
                    continue

                if enviar_telegram(msg):
                    alertas_enviadas += 1
                    log_trades.append(
                        f"{nombre} {direccion} score:{score}"
                    )
                    if registrar_trade(
                        historial,
                        symbol         = symbol,
                        nombre         = nombre,
                        direccion      = direccion,
                        score          = score,
                        precio_entrada = precio,
                        tp             = tp,
                        sl             = sl,
                        timeframe      = "1H/4H",
                        razon_list     = razones,
                        nivel_mart     = nivel_mart,
                        metricas       = metricas,
                    ):
                        existing_ids.add(sid)

                    guardar_historial(historial)
                    sincronizar_sheets(historial)
                    time.sleep(1)

                # Solo la mejor señal por par (no spamear LONG y SHORT del mismo)
                break

        # ── Mensaje de resumen ────────────────────────────────
        guardar_historial(historial)
        pendientes = historial["stats"]["pendientes"]
        stats      = calcular_stats(historial)
        stats_txt  = formatear_stats(stats)

        if alertas_enviadas == 0:
            enviar_telegram(
                f"🔍 <b>TradeBot v1.0</b>\n\n"
                f"📅 {safe_html(ahora)} (Colombia)\n"
                f"📊 Analicé {len(PARES)} pares | "
                f"Score mínimo: {SCORE_MINIMO}\n"
                f"❌ Ningún par superó el umbral\n\n"
                f"{stats_txt}\n\n"
                f"⏰ Próximo análisis en 1 hora"
            )
        else:
            detalle = "\n".join(f"  · {t}" for t in log_trades)
            enviar_telegram(
                f"✅ <b>TradeBot v1.0 — {safe_html(alertas_enviadas)} señal(es)</b>\n\n"
                f"📅 {safe_html(ahora)} (Colombia)\n"
                f"<b>Alertas enviadas:</b>\n{detalle}\n\n"
                f"{stats_txt}"
            )

        logger.info(f"✅ Fin — {alertas_enviadas} señales | Mart nivel:{nivel_mart}")

        # ── Cierre del día ────────────────────────────────────
        if es_bloque_cierre():
            logger.info("🌙 Bloque cierre — resumen Gemini + backup...")
            analisis_diario_gemini(historial)
            backup_historial_github()

    except Exception as e:
        logger.critical(f"❌ Error crítico: {type(e).__name__}: {e}")
        enviar_telegram(
            f"❌ <b>ERROR CRÍTICO TradeBot v1.0</b>\n"
            f"{type(e).__name__}: {str(e)[:150]}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
