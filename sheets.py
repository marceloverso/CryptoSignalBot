# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — sheets.py
#  Google Sheets — registro de trades.
#
#  COLUMNAS:
#  #, Fecha, Hora, Par, Dirección, Score, TF,
#  Entrada, TP, SL, R/R, ¿Entré?, Stake,
#  Resultado, W-L, G.Neta, Balance
# ═══════════════════════════════════════════════════════════════

import json, logging
from config import GSHEETS_CREDS, GSHEETS_SHEET_ID, CAPITAL

logger = logging.getLogger(__name__)

HEADERS = [
    "#","Fecha","Hora","Par","Dir","Score","TF",
    "Entrada","TP","SL","R/R","¿Entré?",
    "Stake","Resultado","W-L","G.Neta","Balance",
]
COL_WIDTHS = [35,100,60,85,65,55,50,95,95,95,55,70,85,90,50,100,110]
LAST_COL   = "Q"


def _fmt(bold=False, fg=None, bg=None, size=10, halign="CENTER") -> dict:
    f = {"horizontalAlignment": halign,
         "textFormat": {"bold": bold, "fontSize": size}}
    if fg:
        r,g,b = int(fg[0:2],16)/255, int(fg[2:4],16)/255, int(fg[4:6],16)/255
        f["textFormat"]["foregroundColor"] = {"red":r,"green":g,"blue":b}
    if bg:
        r,g,b = int(bg[0:2],16)/255, int(bg[2:4],16)/255, int(bg[4:6],16)/255
        f["backgroundColor"] = {"red":r,"green":g,"blue":b}
    return f


def _limpiar_hoja(sh, ws):
    try:
        sh.batch_update({"requests": [
            {"updateCells": {
                "range": {"sheetId": ws.id, "startRowIndex":0, "startColumnIndex":0},
                "fields": "userEnteredValue"}},
            {"repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex":0, "startColumnIndex":0},
                "cell": {"userEnteredFormat": {
                    "backgroundColor":    {"red":1,"green":1,"blue":1},
                    "horizontalAlignment": "LEFT",
                    "textFormat": {"bold":False,"fontSize":10,
                                   "foregroundColor":{"red":0,"green":0,"blue":0}},
                }},
                "fields": "userEnteredFormat"}},
        ]})
    except Exception as e:
        logger.warning(f"⚠️ _limpiar_hoja: {e}")
        try: ws.clear()
        except: pass


def _nombre_mes(fecha_str: str) -> str:
    meses = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
             7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
    try: return meses.get(int(fecha_str[5:7]),"Mes")
    except: return "Mes"


def sincronizar_sheets(historial: dict) -> bool:
    if not GSHEETS_CREDS or not GSHEETS_SHEET_ID:
        logger.info("📊 Sheets: secrets no configurados")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_info(
            json.loads(GSHEETS_CREDS),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GSHEETS_SHEET_ID)

        trades = historial.get("trades", [])
        if not trades: return False

        apostados_ids = set(historial.get("apostados_ids", []))

        # Agrupar por mes
        por_mes: dict = {}
        for t in trades:
            mes = _nombre_mes(t.get("fecha",""))
            por_mes.setdefault(mes, []).append(t)

        for mes, ames in por_mes.items():
            ames_s = sorted(ames, key=lambda x: (x.get("fecha",""), x.get("hora","")))
            n = len(ames_s)

            try:
                ws = sh.worksheet(mes)
                # Leer ¿Entré? antes de limpiar
                try:
                    vals = ws.col_values(12)  # columna L
                    for i in range(1, min(n+1, len(vals))):
                        if vals[i].strip().upper() == "Y":
                            apostados_ids.add(ames_s[i-1].get("id",""))
                except: pass
                _limpiar_hoja(sh, ws)
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=mes, rows=500, cols=20)

        historial["apostados_ids"] = list(apostados_ids)

        for mes, ames in por_mes.items():
            try: ws = sh.worksheet(mes)
            except: ws = sh.add_worksheet(title=mes, rows=500, cols=20)

            ames_s = sorted(ames, key=lambda x: (x.get("fecha",""), x.get("hora","")))
            all_rows = [HEADERS]
            balance_ap = CAPITAL

            for idx, t in enumerate(ames_s, 1):
                estado   = t.get("estado","pendiente")
                apostado = t.get("id","") in apostados_ids
                entrada  = t.get("precio_entrada",0)
                tp       = t.get("tp",0)
                sl       = t.get("sl",0)
                rr       = round(abs((tp-entrada)/(entrada-sl)),2) if entrada!=sl else "?"
                gan_neta = t.get("ganancia_real",0) if (apostado and estado!="pendiente") else ""
                bal      = ""
                if apostado and isinstance(gan_neta,(int,float)):
                    balance_ap += gan_neta
                    bal = balance_ap

                wl = ("W" if estado=="ganada" else "L" if estado=="perdida" else "")

                precio_c = t.get("precio_cierre","")
                res_txt  = (
                    f"{precio_c}" if precio_c and estado!="pendiente"
                    else ("pend." if estado=="pendiente" else "")
                )

                all_rows.append([
                    idx,
                    t.get("fecha",""),
                    t.get("hora",""),
                    t.get("nombre",""),
                    t.get("direccion",""),
                    t.get("score",""),
                    t.get("timeframe",""),
                    entrada, tp, sl, rr,
                    "Y" if apostado else "",
                    t.get("stake","") if apostado else "",
                    res_txt, wl,
                    gan_neta, bal,
                ])

            # Totales
            n2 = len(ames_s)
            res_all  = [t for t in ames_s if t.get("estado")!="pendiente"]
            gano_all = sum(1 for t in res_all if t["estado"]=="ganada")
            wr_all   = f"{round(gano_all/len(res_all)*100,1)}%" if res_all else "-"
            res_ap   = [t for t in res_all if t.get("id","") in apostados_ids]
            gano_ap  = sum(1 for t in res_ap if t["estado"]=="ganada")
            wr_ap    = f"{round(gano_ap/len(res_ap)*100,1)}%" if res_ap else "-"
            gan_ap   = sum(t.get("ganancia_real",0) for t in res_ap)
            stk_ap   = sum(t.get("stake",0) for t in res_ap) or 1
            roi_ap   = round(gan_ap/stk_ap*100,1) if res_ap else 0

            all_rows.append(["", f"TOTAL ALERTAS — {mes}",
                f"{gano_all}W/{len(res_all)-gano_all}L", f"WR {wr_all}",
                "","","","","","","","","","","","",""])
            all_rows.append(["", f"ENTRADAS — {mes}",
                f"{gano_ap}W/{len(res_ap)-gano_ap}L", f"WR {wr_ap}",
                f"ROI {roi_ap}%","","","","","","",
                "",stk_ap if res_ap else "","","",
                gan_ap or "", balance_ap])

            ws.update("A1", all_rows, value_input_option="USER_ENTERED")
            ws.freeze(rows=1)

            # Formatos
            fmt_reqs = [
                {"range": f"A1:{LAST_COL}1",
                 "format": _fmt(bold=True, fg="FFFFFF", bg="0D1117", size=10)},
                {"range": f"A{n2+2}:{LAST_COL}{n2+2}",
                 "format": _fmt(bold=True, fg="FFFFFF", bg="1F6FEB", size=10)},
                {"range": f"A{n2+3}:{LAST_COL}{n2+3}",
                 "format": _fmt(bold=True, fg="FFFFFF", bg="238636", size=10)},
            ]

            for ri, t in enumerate(ames_s, 2):
                estado   = t.get("estado","pendiente")
                apostado = t.get("id","") in apostados_ids
                bg = ("D9EAD3" if estado=="ganada"
                      else "F4CCCC" if estado=="perdida"
                      else "F8F9FA" if ri%2==0 else "FFFFFF")
                fmt_reqs.append({"range":f"A{ri}:{LAST_COL}{ri}",
                                  "format":_fmt(bg=bg, size=9)})
                # Dirección LONG/SHORT
                dir_fg = "274E13" if t.get("direccion")=="LONG" else "CC0000"
                fmt_reqs.append({"range":f"E{ri}","format":_fmt(bold=True,fg=dir_fg,bg=bg,size=9)})
                # ¿Entré?
                if apostado:
                    fmt_reqs.append({"range":f"L{ri}","format":_fmt(bold=True,fg="7F4F00",bg="FFE599",size=9)})
                # W-L
                wl = "W" if estado=="ganada" else "L" if estado=="perdida" else ""
                if wl=="W": fmt_reqs.append({"range":f"O{ri}","format":_fmt(bold=True,fg="274E13",bg=bg,size=9)})
                elif wl=="L": fmt_reqs.append({"range":f"O{ri}","format":_fmt(bold=True,fg="CC0000",bg=bg,size=9)})

            try: ws.batch_format(fmt_reqs)
            except AttributeError: pass

            dim_reqs = []
            for ci, w in enumerate(COL_WIDTHS):
                dim_reqs.append({"updateDimensionProperties":{
                    "range":{"sheetId":ws.id,"dimension":"COLUMNS",
                             "startIndex":ci,"endIndex":ci+1},
                    "properties":{"pixelSize":w},"fields":"pixelSize"}})
            sh.batch_update({"requests": dim_reqs})

        logger.info(f"✅ Sheets sincronizado: {len(trades)} trades | {len(por_mes)} mes(es)")
        return True

    except Exception as e:
        logger.error(f"❌ sheets: {type(e).__name__}: {e}")
        return False
