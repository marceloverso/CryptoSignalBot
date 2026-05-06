# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — historial.py
#  CRUD del historial, dedup, stats y verificación TP/SL.
#  90% igual al bot de apuestas — adaptado para trades.
# ═══════════════════════════════════════════════════════════════

import json, logging, time
from datetime import timedelta
from config import HISTORIAL_F, CAPITAL, MART_MAX_NIVEL, calcular_stake
from utils  import build_signal_id, ahora_colombia, fecha_colombia

logger = logging.getLogger(__name__)

_MART_DEFAULT = {"nivel":1, "racha_perdidas":0, "activa":True, "stop_notificado":False}

def ensure_historial(h) -> dict:
    if not isinstance(h, dict): h = {}
    h.setdefault("trades", [])
    h.setdefault("apostados_ids", [])
    h.setdefault("martingala", dict(_MART_DEFAULT))
    for k, v in _MART_DEFAULT.items():
        h["martingala"].setdefault(k, v)
    # Recalcular stats siempre
    trades = h["trades"]
    h["stats"] = {
        "total":        len(trades),
        "ganadas":      sum(1 for t in trades if t.get("estado") == "ganada"),
        "perdidas":     sum(1 for t in trades if t.get("estado") == "perdida"),
        "pendientes":   sum(1 for t in trades if t.get("estado") == "pendiente"),
        "ganancia_neta": sum(
            t.get("ganancia_real", 0) for t in trades
            if t.get("estado") in ("ganada","perdida")
            and isinstance(t.get("ganancia_real"), (int,float))
        ),
    }
    return h

def cargar_historial() -> dict:
    if HISTORIAL_F.exists():
        try:
            with open(HISTORIAL_F, "r", encoding="utf-8") as f:
                return ensure_historial(json.load(f))
        except Exception as e:
            logger.warning(f"⚠️ Error cargando historial: {e}")
    return ensure_historial({})

def guardar_historial(h: dict) -> None:
    try:
        h = ensure_historial(h)
        with open(HISTORIAL_F, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Historial: {len(h['trades'])} trades | {h['stats']['pendientes']} pendientes")
    except Exception as e:
        logger.error(f"❌ guardar_historial: {e}")

def registrar_trade(h, symbol, nombre, direccion, score, precio_entrada,
                    tp, sl, timeframe, razon_list, nivel_mart=1,
                    metricas=None) -> bool:
    h = ensure_historial(h)
    ts = int(ahora_colombia().timestamp() * 1000)
    tid = build_signal_id(symbol, direccion, timeframe, ts)
    if tid in {t.get("id") for t in h["trades"]}:
        logger.info(f"↩️ Duplicado: {symbol} {direccion}")
        return False

    stake = calcular_stake(nivel_mart)
    ganancia_pot = round(stake * ((tp/precio_entrada) - 1)) if direccion == "LONG" \
        else round(stake * (1 - (tp/precio_entrada)))
    perdida_max = round(stake * abs((precio_entrada - sl) / precio_entrada))

    h["trades"].append({
        "id":             tid,
        "fecha":          fecha_colombia(),
        "hora":           ahora_colombia().strftime("%H:%M"),
        "symbol":         symbol,
        "nombre":         nombre,
        "direccion":      direccion,
        "score":          score,
        "timeframe":      timeframe,
        "precio_entrada": precio_entrada,
        "tp":             tp,
        "sl":             sl,
        "stake":          stake,
        "ganancia_pot":   ganancia_pot,
        "perdida_max":    perdida_max,
        "estado":         "pendiente",   # pendiente | ganada | perdida
        "precio_cierre":  None,
        "ganancia_real":  0,
        "nivel_martingala": nivel_mart,
        "razones":        razon_list,
        "metricas":       metricas or {},
        "martingala_procesado": False,
    })
    logger.info(f"📝 Trade registrado: {symbol} {direccion} | score:{score} | M:{nivel_mart} | stake:${stake:,}")
    return True

def verificar_resultados(h: dict) -> int:
    """
    A diferencia de apuestas, los resultados de trading se verifican
    consultando el precio actual y comparando con TP/SL.
    Las operaciones se consideran "expiradas" después de 48h si no tocaron TP/SL.
    """
    from market_data import get_ticker_24h
    pendientes = [t for t in h["trades"] if t["estado"] == "pendiente"]
    if not pendientes:
        return 0

    actualizadas = 0
    ahora = ahora_colombia()
    cutoff_48h = (ahora - timedelta(hours=48)).strftime("%Y-%m-%d")

    for trade in pendientes:
        # Timeout 48h — cierra al precio actual como perdida parcial
        if trade.get("fecha", "9999") < cutoff_48h:
            ticker = get_ticker_24h(trade["symbol"])
            precio_cierre = ticker["precio_actual"] if ticker else trade["precio_entrada"]
            trade["precio_cierre"] = precio_cierre
            if trade["direccion"] == "LONG":
                gan = round(trade["stake"] * ((precio_cierre / trade["precio_entrada"]) - 1))
            else:
                gan = round(trade["stake"] * (1 - (precio_cierre / trade["precio_entrada"])))
            trade["estado"]       = "ganada" if gan > 0 else "perdida"
            trade["ganancia_real"] = gan
            actualizadas += 1
            logger.info(f"⏰ Timeout: {trade['symbol']} → {trade['estado']} ${gan:,}")
            continue

        # Verificar precio actual vs TP/SL
        ticker = get_ticker_24h(trade["symbol"])
        if not ticker:
            continue
        precio = ticker["precio_actual"]
        tp, sl = trade["tp"], trade["sl"]

        if trade["direccion"] == "LONG":
            if precio >= tp:
                gan = trade["ganancia_pot"]
                trade["estado"] = "ganada"
            elif precio <= sl:
                gan = -trade["perdida_max"]
                trade["estado"] = "perdida"
            else:
                continue
        else:  # SHORT
            if precio <= tp:
                gan = trade["ganancia_pot"]
                trade["estado"] = "ganada"
            elif precio >= sl:
                gan = -trade["perdida_max"]
                trade["estado"] = "perdida"
            else:
                continue

        trade["precio_cierre"]  = precio
        trade["ganancia_real"]  = gan
        actualizadas += 1
        logger.info(f"📊 {trade['symbol']} {trade['direccion']} → {trade['estado'].upper()} ${gan:,}")

    return actualizadas

def actualizar_martingala(h: dict) -> bool:
    h = ensure_historial(h)
    mart = h["martingala"]
    no_proc = [
        t for t in h["trades"]
        if t.get("estado") in ("ganada","perdida")
        and not t.get("martingala_procesado", False)
    ]
    no_proc.sort(key=lambda x: (x.get("fecha",""), x.get("hora","")))
    if not no_proc: return False

    for t in no_proc:
        t["martingala_procesado"] = True
        if t["estado"] == "perdida":
            mart["racha_perdidas"] += 1
            mart["nivel"] = min(mart["racha_perdidas"] + 1, MART_MAX_NIVEL)
            if mart["racha_perdidas"] >= MART_MAX_NIVEL:
                mart["activa"] = False
        else:
            mart["racha_perdidas"] = 0
            mart["nivel"]          = 1
            mart["activa"]         = True
            mart["stop_notificado"]= False
    return True

def necesita_stop_alert(h) -> bool:
    m = h.get("martingala", {})
    return not m.get("activa", True) and not m.get("stop_notificado", False)

def marcar_stop_notificado(h):
    h["martingala"]["stop_notificado"] = True

def calcular_stats(h: dict) -> dict | None:
    trades = h.get("trades", [])
    resueltos = [t for t in trades if t.get("estado") in ("ganada","perdida")]
    if not resueltos: return None

    ganadas  = [t for t in resueltos if t["estado"] == "ganada"]
    gan_neta = sum(t.get("ganancia_real",0) for t in resueltos)
    staked   = sum(t.get("stake",0) for t in resueltos) or 1
    balance  = CAPITAL + gan_neta

    # Por score
    def seg(mn, mx):
        s = [t for t in resueltos if mn <= t.get("score",0) < mx]
        if not s: return None
        w = sum(1 for t in s if t["estado"]=="ganada")
        gn = sum(t.get("ganancia_real",0) for t in s)
        st = sum(t.get("stake",0) for t in s) or 1
        return {"total":len(s),"ganadas":w,"wr":round(w/len(s)*100,1),"roi":round(gn/st*100,1)}

    # Drawdown
    bal, pico, max_dd = CAPITAL, CAPITAL, 0
    for t in sorted(resueltos, key=lambda x: (x.get("fecha",""),x.get("hora",""))):
        bal += t.get("ganancia_real",0)
        if bal > pico: pico = bal
        dd = pico - bal
        if dd > max_dd: max_dd = dd

    # Rachas
    racha_l = racha_w = cur_l = cur_w = 0
    for t in sorted(resueltos, key=lambda x: (x.get("fecha",""),x.get("hora",""))):
        if t["estado"] == "perdida": cur_l+=1; cur_w=0
        else:                        cur_w+=1; cur_l=0
        racha_l = max(racha_l, cur_l)
        racha_w = max(racha_w, cur_w)

    pend = sum(1 for t in trades if t.get("estado") == "pendiente")

    return {
        "total":        len(resueltos),
        "ganadas":      len(ganadas),
        "wr":           round(len(ganadas)/len(resueltos)*100,1),
        "roi":          round(gan_neta/staked*100,1),
        "gan_neta":     gan_neta,
        "balance":      balance,
        "pico":         pico,
        "max_dd":       max_dd,
        "max_dd_pct":   round(max_dd/pico*100,1) if pico else 0,
        "dd_actual":    pico - balance,
        "racha_l_max":  racha_l,
        "racha_w_max":  racha_w,
        "score_70_79":  seg(70,80),
        "score_80_89":  seg(80,90),
        "score_90":     seg(90,101),
        "pendientes":   pend,
    }
