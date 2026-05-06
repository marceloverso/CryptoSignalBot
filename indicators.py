# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — indicators.py
#  Indicadores técnicos + scoring de señales.
#  Equivalente a scoring.py del bot de apuestas.
#
#  INDICADORES:
#  - RSI(14)         momentum: sobrecompra/sobreventa
#  - EMA 20/50/200   tendencia: cruce dorado/muerto
#  - MACD            momentum: divergencia alcista/bajista
#  - Bollinger Bands volatilidad: precio en banda
#  - ATR(14)         volatilidad real: calcula TP/SL dinámicos
#  - Volumen         consenso: volumen sobre/bajo promedio
#
#  SCORE 0-100:
#  Cada indicador aporta puntos si confirma la dirección.
#  Similar al draw score del bot: suma de componentes con razones.
# ═══════════════════════════════════════════════════════════════

import logging
import math

logger = logging.getLogger(__name__)


# ─── HELPERS ──────────────────────────────────────────────────
def _closes(velas: list[dict]) -> list[float]:
    return [v["close"] for v in velas]

def _highs(velas: list[dict]) -> list[float]:
    return [v["high"] for v in velas]

def _lows(velas: list[dict]) -> list[float]:
    return [v["low"] for v in velas]

def _volumes(velas: list[dict]) -> list[float]:
    return [v["volume"] for v in velas]


# ─── INDICADORES PUROS ────────────────────────────────────────
def calcular_ema(valores: list[float], periodo: int) -> list[float]:
    if len(valores) < periodo:
        return []
    k = 2 / (periodo + 1)
    ema = [sum(valores[:periodo]) / periodo]
    for v in valores[periodo:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def calcular_rsi(closes: list[float], periodo: int = 14) -> float | None:
    if len(closes) < periodo + 1:
        return None
    deltas  = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    ganancias = [max(d, 0) for d in deltas[-periodo:]]
    perdidas  = [abs(min(d, 0)) for d in deltas[-periodo:]]
    avg_g = sum(ganancias) / periodo
    avg_p = sum(perdidas)  / periodo
    if avg_p == 0:
        return 100.0
    rs = avg_g / avg_p
    return round(100 - (100 / (1 + rs)), 2)


def calcular_macd(closes: list[float]) -> tuple[float, float, float] | None:
    """Retorna (macd_line, signal_line, histogram)."""
    if len(closes) < 35:
        return None
    ema12 = calcular_ema(closes, 12)
    ema26 = calcular_ema(closes, 26)
    if not ema12 or not ema26:
        return None
    # Alinear
    diff = len(ema12) - len(ema26)
    ema12 = ema12[diff:] if diff > 0 else ema12
    macd_line = [ema12[i] - ema26[i] for i in range(len(ema26))]
    signal    = calcular_ema(macd_line, 9)
    if not signal:
        return None
    diff2      = len(macd_line) - len(signal)
    ml_aligned = macd_line[diff2:]
    histogram  = [ml_aligned[i] - signal[i] for i in range(len(signal))]
    return round(ml_aligned[-1], 6), round(signal[-1], 6), round(histogram[-1], 6)


def calcular_bollinger(closes: list[float], periodo: int = 20,
                       desv: float = 2.0) -> tuple[float, float, float] | None:
    """Retorna (banda_alta, media, banda_baja)."""
    if len(closes) < periodo:
        return None
    ventana = closes[-periodo:]
    media   = sum(ventana) / periodo
    std     = math.sqrt(sum((x - media)**2 for x in ventana) / periodo)
    return round(media + desv * std, 6), round(media, 6), round(media - desv * std, 6)


def calcular_atr(velas: list[dict], periodo: int = 14) -> float | None:
    """Average True Range — para calcular TP/SL dinámicos."""
    if len(velas) < periodo + 1:
        return None
    trs = []
    for i in range(1, len(velas)):
        h = velas[i]["high"]
        l = velas[i]["low"]
        c_prev = velas[i-1]["close"]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    return round(sum(trs[-periodo:]) / periodo, 6)


# ─── SCORE PRINCIPAL ──────────────────────────────────────────
def calcular_score(
    datos: dict,
    direccion: str = "LONG",   # "LONG" o "SHORT"
) -> tuple[int, list[str], list[str], dict]:
    """
    Calcula el score de una señal de trading (0-100).

    Retorna: (score, razones, rechazos, metricas)
    - score:    puntuación final 0-100
    - razones:  lista de strings explicando cada componente
    - rechazos: motivos por los que se descarta (si no está vacía → ignorar)
    - metricas: dict con todos los valores calculados (para el mensaje)

    COMPONENTES:
    1. Tendencia EMA     (hasta 25 pts)
    2. RSI               (hasta 20 pts)
    3. MACD              (hasta 20 pts)
    4. Bollinger Bands   (hasta 15 pts)
    5. Volumen           (hasta 10 pts)
    6. Confirmación 4H   (hasta 10 pts)
    """
    try:
        velas_1h = datos.get("velas_1h", [])
        velas_4h = datos.get("velas_4h", [])
        precio   = datos.get("precio", 0)

        if len(velas_1h) < 30:
            return 0, [], ["datos insuficientes"], {}

        closes_1h = _closes(velas_1h)
        score: int    = 0
        razones: list = []
        rechazos: list= []
        metricas: dict= {}
        es_long = (direccion == "LONG")

        # ── 1. Tendencia EMA ──────────────────────────────────
        ema20  = calcular_ema(closes_1h, 20)
        ema50  = calcular_ema(closes_1h, 50)
        ema200 = calcular_ema(closes_1h, 200) if len(closes_1h) >= 200 else []

        ema20_val  = ema20[-1]  if ema20  else None
        ema50_val  = ema50[-1]  if ema50  else None
        ema200_val = ema200[-1] if ema200 else None

        metricas["ema20"]  = ema20_val
        metricas["ema50"]  = ema50_val
        metricas["ema200"] = ema200_val

        if ema20_val and ema50_val:
            cruce_dorado  = ema20_val > ema50_val
            precio_arriba = precio > ema20_val

            if es_long:
                if cruce_dorado and precio_arriba:
                    pts, txt = 25, "EMA20 > EMA50 + precio sobre EMA20 (tendencia alcista)"
                elif cruce_dorado:
                    pts, txt = 15, "EMA20 > EMA50 (tendencia alcista, precio retrocediendo)"
                elif precio_arriba:
                    pts, txt = 8,  "Precio sobre EMA20 pero sin cruce (momentum mixto)"
                else:
                    pts, txt = 0,  "EMA20 < EMA50 (tendencia bajista)"
                    rechazos.append("tendencia bajista en 1H")
            else:  # SHORT
                if not cruce_dorado and not precio_arriba:
                    pts, txt = 25, "EMA20 < EMA50 + precio bajo EMA20 (tendencia bajista)"
                elif not cruce_dorado:
                    pts, txt = 15, "EMA20 < EMA50 (tendencia bajista confirmada)"
                else:
                    pts, txt = 0,  "Tendencia alcista activa"
                    rechazos.append("tendencia alcista contraría SHORT")

            score += pts
            razones.append(f"EMA 20/50: {txt}: +{pts}")

        # ── 2. RSI ────────────────────────────────────────────
        rsi = calcular_rsi(closes_1h)
        metricas["rsi"] = rsi

        if rsi is not None:
            if es_long:
                if   40 <= rsi <= 60: pts, txt = 20, "RSI en zona neutral (40-60) — sin sobrecompra"
                elif 30 <= rsi < 40:  pts, txt = 18, "RSI en zona de valor (30-40) — momentum acumulando"
                elif rsi < 30:        pts, txt = 15, f"RSI sobrevendido ({rsi}) — posible rebote"
                elif 60 < rsi <= 70:  pts, txt = 8,  "RSI elevado (60-70) — cuidado con sobrecompra"
                else:                 pts, txt = 0,  f"RSI sobrecomprado ({rsi}) — evitar LONG"
            else:  # SHORT
                if   40 <= rsi <= 60: pts, txt = 20, "RSI neutral — sin sobrecompra clara"
                elif 60 < rsi <= 70:  pts, txt = 18, "RSI en zona de distribución (60-70)"
                elif rsi > 70:        pts, txt = 15, f"RSI sobrecomprado ({rsi}) — posible caída"
                elif 30 <= rsi < 40:  pts, txt = 5,  "RSI bajo — SHORT menos favorable"
                else:                 pts, txt = 0,  f"RSI sobrevendido ({rsi}) — evitar SHORT"

            score += pts
            razones.append(f"RSI(14)={rsi}: {txt}: +{pts}")

        # ── 3. MACD ───────────────────────────────────────────
        macd_result = calcular_macd(closes_1h)
        if macd_result:
            macd_line, signal_line, histogram = macd_result
            metricas["macd"]      = macd_line
            metricas["macd_sig"]  = signal_line
            metricas["macd_hist"] = histogram

            if es_long:
                if macd_line > signal_line and histogram > 0:
                    pts, txt = 20, "MACD > Signal y histograma positivo (momentum alcista)"
                elif macd_line > signal_line:
                    pts, txt = 12, "MACD > Signal (cruce alcista reciente)"
                elif histogram > 0:
                    pts, txt = 8,  "Histograma positivo (momentum mejorando)"
                else:
                    pts, txt = 0,  "MACD bajista"
            else:
                if macd_line < signal_line and histogram < 0:
                    pts, txt = 20, "MACD < Signal y histograma negativo (momentum bajista)"
                elif macd_line < signal_line:
                    pts, txt = 12, "MACD < Signal (cruce bajista reciente)"
                else:
                    pts, txt = 0,  "MACD alcista — contradice SHORT"

            score += pts
            razones.append(f"MACD({round(macd_line,4)}): {txt}: +{pts}")

        # ── 4. Bollinger Bands ────────────────────────────────
        bb = calcular_bollinger(closes_1h)
        if bb:
            bb_high, bb_mid, bb_low = bb
            metricas["bb_high"] = bb_high
            metricas["bb_mid"]  = bb_mid
            metricas["bb_low"]  = bb_low
            ancho_bb = round((bb_high - bb_low) / bb_mid * 100, 1)
            metricas["bb_ancho_pct"] = ancho_bb

            if es_long:
                if precio < bb_mid and precio > bb_low:
                    pts, txt = 15, f"Precio entre BB media y BB baja — zona de valor LONG"
                elif precio > bb_mid:
                    pts, txt = 8,  "Precio sobre BB media — tendencia alcista"
                elif precio <= bb_low:
                    pts, txt = 12, "Precio en BB baja — posible rebote (LONG)"
                else:
                    pts, txt = 0,  "Precio en BB alta — sobrecompra"
            else:
                if precio > bb_mid and precio < bb_high:
                    pts, txt = 15, "Precio entre BB media y BB alta — zona de distribución SHORT"
                elif precio >= bb_high:
                    pts, txt = 12, "Precio en BB alta — posible reversión (SHORT)"
                else:
                    pts, txt = 5,  "Precio bajo BB media — SHORT menos favorable"

            score += pts
            razones.append(f"Bollinger({round(bb_mid,2)}±{ancho_bb}%): {txt}: +{pts}")

        # ── 5. Volumen ────────────────────────────────────────
        volumes = _volumes(velas_1h)
        if len(volumes) >= 20:
            vol_actual  = volumes[-1]
            vol_promedio = sum(volumes[-20:]) / 20
            ratio_vol   = round(vol_actual / vol_promedio, 2) if vol_promedio > 0 else 1
            metricas["vol_ratio"] = ratio_vol

            if   ratio_vol >= 2.0: pts, txt = 10, f"Volumen x{ratio_vol} sobre promedio (confirmación fuerte)"
            elif ratio_vol >= 1.5: pts, txt = 8,  f"Volumen x{ratio_vol} sobre promedio (confirmación sólida)"
            elif ratio_vol >= 1.2: pts, txt = 5,  f"Volumen x{ratio_vol} ligeramente elevado"
            elif ratio_vol >= 0.8: pts, txt = 2,  f"Volumen normal (x{ratio_vol})"
            else:                  pts, txt = 0,  f"Volumen bajo (x{ratio_vol}) — señal débil"

            score += pts
            razones.append(f"Volumen {ratio_vol}x promedio: {txt}: +{pts}")

        # ── 6. Confirmación 4H ────────────────────────────────
        if velas_4h and len(velas_4h) >= 20:
            closes_4h = _closes(velas_4h)
            ema20_4h  = calcular_ema(closes_4h, 20)
            rsi_4h    = calcular_rsi(closes_4h)

            if ema20_4h:
                precio_sobre_4h = precio > ema20_4h[-1]
                rsi_ok_4h = (
                    (es_long  and rsi_4h and rsi_4h < 70) or
                    (not es_long and rsi_4h and rsi_4h > 30)
                ) if rsi_4h else True

                if es_long and precio_sobre_4h and rsi_ok_4h:
                    pts, txt = 10, "4H confirma: precio sobre EMA20(4H) + RSI sano"
                elif not es_long and not precio_sobre_4h and rsi_ok_4h:
                    pts, txt = 10, "4H confirma: precio bajo EMA20(4H) + RSI sano"
                elif (es_long and precio_sobre_4h) or (not es_long and not precio_sobre_4h):
                    pts, txt = 5,  "4H parcialmente confirma la dirección"
                else:
                    pts, txt = 0,  "4H no confirma — tendencias divergentes"

                metricas["ema20_4h"] = ema20_4h[-1]
                metricas["rsi_4h"]   = rsi_4h
                score += pts
                razones.append(f"Confirmación 4H: {txt}: +{pts}")

        # ── ATR para TP/SL ────────────────────────────────────
        atr = calcular_atr(velas_1h)
        metricas["atr"] = atr

        return min(score, 100), razones, rechazos, metricas

    except Exception as e:
        logger.error(f"❌ calcular_score: {e}")
        return 0, [], [f"error: {e}"], {}


def calcular_tp_sl(precio: float, atr: float | None,
                   direccion: str) -> tuple[float, float]:
    """
    Calcula Take Profit y Stop Loss dinámicos basados en ATR.
    Si no hay ATR disponible, usa % fijos (1.5% TP, 1.0% SL).
    """
    if not atr or atr == 0:
        if direccion == "LONG":
            return round(precio * 1.015, 4), round(precio * 0.990, 4)
        else:
            return round(precio * 0.985, 4), round(precio * 1.010, 4)

    from config import TP_MULTIPLIER, SL_MULTIPLIER
    if direccion == "LONG":
        tp = round(precio + atr * TP_MULTIPLIER, 4)
        sl = round(precio - atr * SL_MULTIPLIER, 4)
    else:
        tp = round(precio - atr * TP_MULTIPLIER, 4)
        sl = round(precio + atr * SL_MULTIPLIER, 4)
    return tp, sl
