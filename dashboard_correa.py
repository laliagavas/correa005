"""
Sistema de Monitoreo de Polines mediante Fibra Óptica
Dashboard — CV005 / CV006 / CV007
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(
    layout="wide",
    page_title="Monitoreo Fibra Óptica — CV",
    page_icon="🔴",
)

# ============================================================
# CONSTANTES
# ============================================================
FACTORES = {
    "CV005": {"troncal": 1.547, "sensitiva": 10.83},
    "CV006": {"troncal": 1.665, "sensitiva": 13.66},
    "CV007": {"troncal": 1.595, "sensitiva": 17.36},
}
EST_RANGES = {
    "CV005": {"min": 1,   "max": 3823},
    "CV006": {"min": -3,  "max": 3526},
    "CV007": {"min": 3,   "max": 842},
}
SENSITIVA_TOTAL_MTS = {"CV005": 41402.0, "CV006": 48214.0, "CV007": 14568.0}
TRONCAL_TOTAL_MTS   = {"CV005": 5916.0,  "CV006": 5876.0,  "CV007": 1339.0}
MAPEO_NUM_A_LETRA   = {-3: "3B Carga", -2: "2B Carga", -1: "1B Carga"}
NIVELES             = {0: "Troncal", 5: "Sensitiva"}
FRENTES             = {"CV005": ["tp1","em"], "CV006": ["tp1","tp2"], "CV007": ["unico"]}
TIPOS_EVENTO        = ["Avance de fibra","Corte","Fusión / empalme","Mantención","Otro"]

# Ítems de avance físico CV005 (instalación de fibra sobre los polines)
ITEMS_AVANCE_FISICO = {
    "fo_posicionada": {"label": "FO Posicionada",       "color": "#06B6D4"},
    "fo_retirada":    {"label": "FO Antigua Retirada",  "color": "#F97316"},
    "clips":          {"label": "Clips Nuevos Pos.",    "color": "#A78BFA"},
    "tejido":         {"label": "FO Tejida",            "color": "#34D399"},
}
TOTAL_EST_CV005 = 3922  # total de estaciones CV005 (1 a 3823 + offset)
TIPOS_AVANCE_FISICO = ["Avance", "Corrección", "Otro"]

# Metros de cabecera (DTS → primera estación) que se suman fijos al metraje
# No dependen del avance registrado — son metros físicos siempre presentes
OFFSET_METROS = {
    "CV005": {"tp1": 122.0, "em": 0.0},   # 122 m desde DTS hasta Est. 3823
    "CV006": {"tp1": 0.0,   "tp2": 0.0},
    "CV007": {"unico": 0.0},
}

# ============================================================
# SUPABASE
# ============================================================
SUPABASE_URL = "https://aumkuyciwmeevnwtsvpy.supabase.co"
SUPABASE_KEY = "sb_publishable_5Iq0mHkNsetilyAFFQo1tw_-dth1liU"

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Error de conexión con Supabase: {e}")
    st.stop()

# ============================================================
# BASE DE DATOS
# ============================================================
def leer_datos(correa_id):
    try:
        resp = (supabase.table("eventos_correa")
                .select("*").eq("correa_id", correa_id)
                .in_("nivel", [0, 5]).execute())
        return pd.DataFrame(resp.data)
    except Exception:
        return pd.DataFrame()

def leer_avance_fisico() -> "pd.DataFrame":
    """Lee todos los registros de avance físico CV005 desde Supabase."""
    try:
        resp = supabase.table("avance_fisico_cv005").select("*").execute()
        return pd.DataFrame(resp.data)
    except Exception:
        return pd.DataFrame()


def guardar_avance_fisico(operador, item, tipo_evento, est_desde, est_hasta, nota) -> bool:
    """Guarda un nuevo registro de avance físico CV005."""
    try:
        supabase.table("avance_fisico_cv005").insert({
            "operador":   operador,
            "item":       item,
            "tipo_evento": tipo_evento,
            "est_desde":  int(est_desde),
            "est_hasta":  int(est_hasta),
            "nota":       nota,
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar avance físico: {e}")
        return False


def calcular_avance_fisico(df_af: "pd.DataFrame") -> dict:
    """
    Por cada ítem suma TODOS los tramos registrados para obtener
    el total acumulado de estaciones y el porcentaje sobre TOTAL_EST_CV005.
    """
    result = {}
    for item_key in ITEMS_AVANCE_FISICO:
        if df_af.empty:
            result[item_key] = {"est": 0, "pct": 0.0}
            continue
        sub = df_af[df_af["item"] == item_key].copy()
        if sub.empty:
            result[item_key] = {"est": 0, "pct": 0.0}
            continue
        # Sumar todos los tramos acumulados
        total_est = int(sub.apply(
            lambda r: abs(int(r["est_hasta"]) - int(r["est_desde"])), axis=1
        ).sum())
        pct = min(total_est / TOTAL_EST_CV005 * 100, 100.0)
        result[item_key] = {"est": total_est, "pct": pct}
    return result


def guardar_registro(operador, desde, hasta, nivel, nota, tipo_evento, correa_id, frente):
    try:
        supabase.table("eventos_correa").insert({
            "operador": operador, "estacion_desde": int(desde),
            "estacion_hasta": int(hasta), "nivel": int(nivel),
            "nota": nota, "tipo_evento": tipo_evento,
            "correa_id": correa_id, "frente": frente,
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False

def leer_historial(limit=50):
    dfs = []
    for cid in ["CV005","CV006","CV007"]:
        df = leer_datos(cid)
        if not df.empty:
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    df_all = pd.concat(dfs, ignore_index=True)
    if "created_at" in df_all.columns:
        df_all["created_at_dt"] = pd.to_datetime(df_all["created_at"], utc=True).dt.tz_convert("America/Santiago")
        df_all = df_all.sort_values("created_at_dt", ascending=False)
    return df_all.head(limit)

# ============================================================
# CÁLCULO
# ============================================================
def obtener_tramo_activo(df, nivel, frente):
    if df.empty:
        return None, None
    sub = df[df["nivel"].astype(int) == nivel].copy()
    if "frente" in sub.columns:
        sub = sub[sub["frente"] == frente]
    if sub.empty:
        return None, None
    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at", ascending=False)
    row = sub.iloc[0]
    return int(row["estacion_desde"]), int(row["estacion_hasta"])


def analizar_estado_frente(df, nivel, frente, correa_id):
    """
    Retorna dict con:
      - desde, hasta: tramo activo actual
      - metros_actuales: metros del tramo actual
      - metros_anteriores: metros del tramo anterior (None si no hay)
      - estado: 'avance' | 'corte' | 'sin_cambio' | 'nuevo'
      - diff_metros: diferencia en metros (positivo=avance, negativo=corte)
      - tipo_evento: tipo del evento más reciente
    """
    if df.empty:
        return None

    sub = df[df["nivel"].astype(int) == nivel].copy()
    if "frente" in sub.columns:
        sub = sub[sub["frente"] == frente]
    if sub.empty:
        return None

    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at", ascending=False)

    factor = FACTORES[correa_id]["troncal"] if nivel == 0 else FACTORES[correa_id]["sensitiva"]
    offset = OFFSET_METROS.get(correa_id, {}).get(frente, 0.0)

    actual   = sub.iloc[0]
    d_act    = int(actual["estacion_desde"])
    h_act    = int(actual["estacion_hasta"])
    mts_act  = abs(h_act - d_act) * factor + offset
    tipo_ev  = str(actual.get("tipo_evento", "")).strip()

    if len(sub) < 2:
        return {
            "desde": d_act, "hasta": h_act,
            "metros_actuales": mts_act, "metros_anteriores": None,
            "estado": "nuevo", "diff_metros": 0, "tipo_evento": tipo_ev,
        }

    anterior = sub.iloc[1]
    d_ant    = int(anterior["estacion_desde"])
    h_ant    = int(anterior["estacion_hasta"])
    mts_ant  = abs(h_ant - d_ant) * factor + offset
    diff     = mts_act - mts_ant

    if abs(diff) < 0.5:
        estado = "sin_cambio"
    elif diff > 0:
        estado = "avance"
    else:
        estado = "corte"

    # Si el tipo_evento dice explícitamente "Corte", forzar estado corte
    if "corte" in tipo_ev.lower():
        estado = "corte"

    return {
        "desde": d_act, "hasta": h_act,
        "metros_actuales": mts_act, "metros_anteriores": mts_ant,
        "estado": estado, "diff_metros": diff, "tipo_evento": tipo_ev,
    }

def calcular_metraje(df, correa_id):
    ft = FACTORES[correa_id]["troncal"]
    fs = FACTORES[correa_id]["sensitiva"]

    metros_s = 0.0
    metros_t = 0.0
    frentes_con_corte = []

    for frente in FRENTES.get(correa_id, ["unico"]):
        offset = OFFSET_METROS.get(correa_id, {}).get(frente, 0.0)

        # Sensitiva: metros de estaciones recorridas + offset de cabecera DTS.
        # Los 122 m son fibra real desplegada (cuentan en el total),
        # solo afectan la conversión metro→estación en la calculadora.
        d, h = obtener_tramo_activo(df, 5, frente)
        if d is not None:
            metros_s += abs(h - d) * fs + offset

        # Troncal
        sub_t = df[df["nivel"].astype(int) == 0].copy() if not df.empty else df
        if not sub_t.empty and "frente" in sub_t.columns:
            sub_t = sub_t[sub_t["frente"] == frente]
        if not sub_t.empty:
            if "created_at" in sub_t.columns:
                sub_t = sub_t.sort_values("created_at", ascending=False)
            ultimo   = sub_t.iloc[0]
            tipo_ev  = str(ultimo.get("tipo_evento", "")).strip().lower()
            d_t, h_t = int(ultimo["estacion_desde"]), int(ultimo["estacion_hasta"])
            tramo_t  = abs(h_t - d_t) * ft

            if "corte" in tipo_ev:
                frentes_con_corte.append(frente)
                metros_t += max(TRONCAL_TOTAL_MTS[correa_id] / len(FRENTES.get(correa_id, ["unico"])) - tramo_t, 0)
            else:
                # Troncal no se ve afectada por el offset de cabecera DTS (es lineal)
                metros_t += TRONCAL_TOTAL_MTS[correa_id] / len(FRENTES.get(correa_id, ["unico"]))
        else:
            metros_t += TRONCAL_TOTAL_MTS[correa_id] / len(FRENTES.get(correa_id, ["unico"]))

    troncal_completa = len(frentes_con_corte) == 0

    if not df.empty and "frente" not in df.columns:
        metros_s = sum(
            abs(int(r["estacion_hasta"]) - int(r["estacion_desde"])) * fs
            for _, r in df[df["nivel"].astype(int) == 5].iterrows()
        )
        metros_t = TRONCAL_TOTAL_MTS[correa_id]
        troncal_completa = True

    total_s = SENSITIVA_TOTAL_MTS[correa_id]
    total_t = TRONCAL_TOTAL_MTS[correa_id]
    metros_t = min(metros_t, total_t)

    return {
        "metros_t":         metros_t,
        "metros_s":         metros_s,
        "pct_t":            (metros_t / total_t * 100) if total_t > 0 else 100.0,
        "pct_s":            min(metros_s / total_s * 100, 100.0) if total_s > 0 else 0.0,
        "total_s":          total_s,
        "total_t":          total_t,
        "factor_t":         ft,
        "factor_s":         fs,
        "troncal_completa": troncal_completa,
    }


# ============================================================
# ESTILOS
# ============================================================
st.markdown("""
<style>
.stAppHeader { display: none !important; }
[data-testid="stMainBlockContainer"] {
    padding-top: 1.4rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
[data-testid="stAppViewContainer"] { background-color: #0D1117; }
[data-testid="stSidebar"] {
    background: #0A0E15 !important;
    border-right: 0.5px solid rgba(255,255,255,0.07) !important;
}
.stButton > button {
    background: rgba(55,138,221,0.1);
    border: 0.5px solid rgba(55,138,221,0.3);
    color: #378ADD; border-radius: 8px;
    font-size: 12px; font-weight: 500;
    width: 100%; padding: 7px 0;
}
.stButton > button:hover {
    background: rgba(55,138,221,0.2);
    border-color: rgba(55,138,221,0.55);
}
hr { border-color: rgba(255,255,255,0.07) !important; }
div[data-testid="stExpander"] {
    background: rgba(255,255,255,0.02) !important;
    border: 0.5px solid rgba(255,255,255,0.07) !important;
    border-radius: 8px !important;
}
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# DATOS
# ============================================================
with st.spinner("Cargando datos…"):
    df_05 = leer_datos("CV005")
    df_06 = leer_datos("CV006")
    df_07 = leer_datos("CV007")
    df_af = leer_avance_fisico()
    av_fis = calcular_avance_fisico(df_af)

met_05 = calcular_metraje(df_05, "CV005")
met_06 = calcular_metraje(df_06, "CV006")
met_07 = calcular_metraje(df_07, "CV007")

# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div style="display:flex;justify-content:space-between;align-items:flex-start;padding:0 0 18px">
  <div>
    <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
                color:rgba(255,255,255,0.3);margin-bottom:5px">
      Centro de telemetría térmica avanzada
    </div>
    <div style="font-size:19px;font-weight:500;color:#F0F2F5">
      Sistema de monitoreo de polines — fibra óptica
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:7px;padding-top:6px">
    <span style="width:7px;height:7px;border-radius:50%;background:#4CAF50;display:inline-block"></span>
    <span style="font-size:11px;color:rgba(255,255,255,0.4)">Sistema en línea</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# KPIs
# ============================================================
total_t    = met_05["metros_t"] + met_06["metros_t"] + met_07["metros_t"]
total_s    = met_05["metros_s"] + met_06["metros_s"] + met_07["metros_s"]
total_s_pos = sum(SENSITIVA_TOTAL_MTS.values())
pct_global = (total_s / total_s_pos * 100) if total_s_pos > 0 else 0

def kpi(label, value, sub, color):
    return f"""
    <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.08);
                border-radius:10px;padding:13px 15px">
      <div style="font-size:10px;color:rgba(255,255,255,0.4);display:flex;align-items:center;
                  gap:6px;margin-bottom:7px;text-transform:uppercase;letter-spacing:.6px">
        <span style="width:7px;height:7px;border-radius:2px;background:{color};display:inline-block"></span>
        {label}
      </div>
      <div style="font-size:21px;font-weight:500;color:#F0F2F5;margin-bottom:4px">{value}</div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3)">{sub}</div>
    </div>"""

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(kpi("Troncal desplegada", f"{total_t:,.0f} m",
        f"CV005: {met_05['metros_t']:,.0f} · CV006: {met_06['metros_t']:,.0f} · CV007: {met_07['metros_t']:,.0f}",
        "#E24B4A"), unsafe_allow_html=True)
with k2:
    st.markdown(kpi("Sensitiva desplegada", f"{total_s:,.0f} m",
        f"CV005: {met_05['metros_s']:,.0f} · CV006: {met_06['metros_s']:,.0f} · CV007: {met_07['metros_s']:,.0f}",
        "#7F77DD"), unsafe_allow_html=True)
with k3:
    correas_ok    = [n for n, m in [("CV005", met_05), ("CV006", met_06), ("CV007", met_07)] if m["troncal_completa"]]
    correas_corte = [n for n, m in [("CV005", met_05), ("CV006", met_06), ("CV007", met_07)] if not m["troncal_completa"]]
    n_ok = len(correas_ok)
    color_kpi3 = "#639922" if n_ok == 3 else "#F59E0B"
    sub_ok    = ", ".join(correas_ok) + " al 100%" if correas_ok else "Ninguna al 100%"
    sub_corte = ("  ·  ⚠ Corte en " + ", ".join(correas_corte)) if correas_corte else ""
    st.markdown(kpi("Troncal completada", f"{n_ok} / 3",
        sub_ok + sub_corte, color_kpi3), unsafe_allow_html=True)
with k4:
    st.markdown(kpi("Cobertura sensitiva global", f"{pct_global:.1f}%",
        f"{total_s:,.0f} m de ~{total_s_pos:,.0f} m", "#BA7517"), unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ============================================================
# CARDS POR CORREA
# ============================================================
st.markdown("""
<div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
            text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
  Estado por correa
</div>
""", unsafe_allow_html=True)

def render_card(col, nombre, met, completada, frentes_txt, av_fis_extra=""):
    color_s = "#639922" if completada else "#7F77DD"
    pct_s   = 100.0 if completada else met["pct_s"]
    pct_t   = met["pct_t"]
    color_t = "#E24B4A" if pct_t >= 100 else "#F59E0B"  # naranja si hay corte/no está al 100%
    border  = "rgba(99,153,34,0.2)" if completada else "rgba(255,255,255,0.08)"
    badge_troncal = "" if pct_t >= 100 else (
        '<span style="font-size:9px;padding:1px 7px;border-radius:99px;'
        'background:rgba(245,158,11,0.15);color:#F59E0B;'
        'border:0.5px solid rgba(245,158,11,0.3);margin-left:6px">⚠ Corte activo</span>'
    )
    badge = (
        '<span style="font-size:10px;padding:2px 9px;border-radius:99px;'
        'background:rgba(99,153,34,0.15);color:#8dc63f;'
        'border:0.5px solid rgba(99,153,34,0.3)">100% completada</span>'
        if completada else
        '<span style="font-size:10px;padding:2px 9px;border-radius:99px;'
        'background:rgba(55,138,221,0.1);color:#378ADD;'
        'border:0.5px solid rgba(55,138,221,0.25)">En progreso</span>'
    )
    bar_t = f"""
    <div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:11px;color:rgba(255,255,255,0.5)">🔴 Troncal{badge_troncal}</span>
        <span style="font-size:11px;font-weight:500;color:{color_t}">{pct_t:.1f}%</span>
      </div>
      <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:6px;overflow:hidden">
        <div style="width:{min(pct_t,100):.1f}%;background:{color_t};height:100%;border-radius:99px"></div>
      </div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-top:3px">
        {met['metros_t']:,.0f} m / ~{met['total_t']:,.0f} m · {met['factor_t']:.2f} m/est
      </div>
    </div>"""
    bar_s = f"""
    <div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:11px;color:rgba(255,255,255,0.5)">🟣 Sensitiva</span>
        <span style="font-size:11px;font-weight:500;color:{color_s}">{pct_s:.1f}%</span>
      </div>
      <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:6px;overflow:hidden">
        <div style="width:{min(pct_s,100):.1f}%;background:{color_s};height:100%;border-radius:99px"></div>
      </div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-top:3px">
        {met['metros_s']:,.0f} m / ~{met['total_s']:,.0f} m · {met['factor_s']:.2f} m/est
      </div>
    </div>"""
    def _badge_frente(estado, diff):
        if estado == "corte":
            return (f'<span style="font-size:9px;padding:1px 6px;border-radius:99px;'
                    f'background:rgba(239,68,68,0.15);color:#F87171;'
                    f'border:0.5px solid rgba(239,68,68,0.3);margin-left:5px">'
                    f'✂ Corte {abs(diff):,.0f} m</span>')
        elif estado == "avance":
            return (f'<span style="font-size:9px;padding:1px 6px;border-radius:99px;'
                    f'background:rgba(34,197,94,0.12);color:#4ADE80;'
                    f'border:0.5px solid rgba(34,197,94,0.25);margin-left:5px">'
                    f'↑ +{diff:,.0f} m</span>')
        return ""

    frente_rows = "".join([
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
        f'<span style="font-size:10px;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:5px">'
        f'<span style="width:5px;height:5px;border-radius:50%;background:{f["color"]};display:inline-block"></span>'
        f'{f["label"]}{_badge_frente(f.get("estado",""), f.get("diff_metros",0))}</span>'
        f'<span style="font-size:10px;color:rgba(255,255,255,0.55)">{f["rango"]}</span></div>'
        for f in frentes_txt
    ])
    html = f"""
    <div style="background:rgba(255,255,255,0.03);border:0.5px solid {border};
                border-radius:12px;padding:15px 16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-size:15px;font-weight:500;color:#F0F2F5">{nombre}</span>{badge}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
        <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:9px 11px">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;
                      color:rgba(255,255,255,0.35);margin-bottom:3px">Troncal</div>
          <div style="font-size:15px;font-weight:500;color:#F0F2F5">{met['metros_t']:,.0f} m</div>
          <div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:2px">100% completa</div>
        </div>
        <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:9px 11px">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;
                      color:rgba(255,255,255,0.35);margin-bottom:3px">Sensitiva</div>
          <div style="font-size:15px;font-weight:500;color:#F0F2F5">{met['metros_s']:,.0f} m</div>
          <div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:2px">de {met['total_s']:,.0f} m</div>
        </div>
      </div>
      {bar_t}{bar_s}
      <div style="border-top:0.5px solid rgba(255,255,255,0.06);padding-top:9px;margin-top:4px">
        {frente_rows}
      </div>
    </div>"""
    with col:
        st.markdown(html, unsafe_allow_html=True)
        if av_fis_extra:
            st.markdown(av_fis_extra, unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)

# ── CV005 frentes con estado ──
est_tp1_05 = analizar_estado_frente(df_05, 5, "tp1", "CV005")
est_em_05  = analizar_estado_frente(df_05, 5, "em",  "CV005")
frentes_05 = []
if est_tp1_05:
    frentes_05.append({"label":"Frente TP1",
                        "rango":f"Est. {est_tp1_05['desde']} → {est_tp1_05['hasta']}",
                        "color":"#E24B4A",
                        "estado": est_tp1_05["estado"],
                        "diff_metros": est_tp1_05["diff_metros"]})
if est_em_05:
    frentes_05.append({"label":"Frente EM",
                        "rango":f"Est. {est_em_05['desde']} → {est_em_05['hasta']}",
                        "color":"#7F77DD",
                        "estado": est_em_05["estado"],
                        "diff_metros": est_em_05["diff_metros"]})
if not frentes_05:
    frentes_05 = [{"label":"Frente TP1","rango":"Est. 3823 → 2000","color":"#E24B4A","estado":"nuevo","diff_metros":0},
                  {"label":"Frente EM", "rango":"Est. 1 → 2000",   "color":"#7F77DD","estado":"nuevo","diff_metros":0}]

# ── CV006 frentes con estado ──
est_tp1_06 = analizar_estado_frente(df_06, 5, "tp1", "CV006")
est_tp2_06 = analizar_estado_frente(df_06, 5, "tp2", "CV006")
frentes_06 = []
if est_tp1_06:
    ld = MAPEO_NUM_A_LETRA.get(est_tp1_06["desde"], str(est_tp1_06["desde"]))
    frentes_06.append({"label":"Frente TP1",
                        "rango":f"{ld} → Est. {est_tp1_06['hasta']}",
                        "color":"#E24B4A",
                        "estado": est_tp1_06["estado"],
                        "diff_metros": est_tp1_06["diff_metros"]})
if est_tp2_06:
    frentes_06.append({"label":"Frente TP2",
                        "rango":f"Est. {est_tp2_06['desde']} → {est_tp2_06['hasta']}",
                        "color":"#7F77DD",
                        "estado": est_tp2_06["estado"],
                        "diff_metros": est_tp2_06["diff_metros"]})
if not frentes_06:
    frentes_06 = [{"label":"Frente TP1","rango":"3B Carga → Est. 1845","color":"#E24B4A","estado":"nuevo","diff_metros":0},
                  {"label":"Frente TP2","rango":"Est. 3526 → 1846",    "color":"#7F77DD","estado":"nuevo","diff_metros":0}]

# ── CV007 ──
est_uni_07 = analizar_estado_frente(df_07, 5, "unico", "CV007")
frentes_07 = [{"label":"Frente único","rango":"Est. 3 → 842","color":"#639922",
               "estado": est_uni_07["estado"] if est_uni_07 else "nuevo",
               "diff_metros": est_uni_07["diff_metros"] if est_uni_07 else 0}]

# ── Gráfico SVG avance físico CV005 ─────────────────────────────────────
def generar_svg_avance_fisico(df_af, df_05_sens, pct_s_real=None):
    """
    Genera el SVG de avance físico CV005 con los tramos reales desde Supabase.
    Niveles (abajo→arriba): Troncal, Sensitiva, FO Pos, FO Ret, Clips, Tejida
    Eje X: 3823 (izq=TP1) → 1 (der=EM)
    """
    W, H   = 700, 230
    X0, X1 = 55, 660   # márgenes eje
    LARGO  = X1 - X0
    EST_MIN, EST_MAX = 1, 3823
    RANGO  = EST_MAX - EST_MIN

    def ex(est):
        """Convierte estación a coordenada X (3823=izq, 1=der)."""
        return X0 + (EST_MAX - max(EST_MIN, min(EST_MAX, int(est)))) / RANGO * LARGO

    # Niveles Y para cada ítem
    NIVELES_Y = {
        "troncal":      195,
        "sensitiva":    170,
        "fo_posicionada": 145,
        "fo_retirada":  120,
        "clips":         95,
        "tejido":        70,
    }
    COLORES = {
        "troncal":        "#E24B4A",
        "sensitiva":      "#7F77DD",
        "fo_posicionada": "#06B6D4",
        "fo_retirada":    "#F97316",
        "clips":          "#A78BFA",
        "tejido":         "#34D399",
    }
    LABELS = {
        "troncal":        "Troncal",
        "sensitiva":      "Sensitiva",
        "fo_posicionada": "FO Posicionada",
        "fo_retirada":    "FO Antigua Ret.",
        "clips":          "Clips Nuevos",
        "tejido":         "FO Tejida",
    }

    parts = [f'<svg width="100%" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Avance físico CV005">']

    # Título
    parts.append(f'<text x="{W/2}" y="18" text-anchor="middle" '
                 f'fill="#F0F2F5" font-size="12" font-weight="500">'
                 f'Avance físico instalación — CV005</text>')

    # Eje X
    parts.append(f'<line x1="{X0}" y1="210" x2="{X1}" y2="210" '
                 f'stroke="#4B5563" stroke-width="1"/>')

    ticks = [3823, 3201, 2601, 2001, 1601, 1201, 801, 401, 1]
    for t in ticks:
        x = ex(t)
        parts.append(f'<line x1="{x:.1f}" y1="208" x2="{x:.1f}" y2="213" stroke="#6B7280"/>')
        parts.append(f'<text x="{x:.1f}" y="223" text-anchor="middle" '
                     f'fill="#6B7280" font-size="8">{t}</text>')

    # Labels TP1 / EM
    parts.append(f'<text x="{X0}" y="232" text-anchor="middle" '
                 f'fill="#9CA3AF" font-size="8" font-weight="500">TP1</text>')
    parts.append(f'<text x="{X1}" y="232" text-anchor="middle" '
                 f'fill="#9CA3AF" font-size="8" font-weight="500">EM</text>')

    # ── Líneas verticales de referencia: Centro instalación Est. 1850 y 1851 ──
    y_top = min(NIVELES_Y.values()) - 10
    y_bot = 210
    for est_ref, label_ref in [(1850, "Est. 1850"), (1851, "Est. 1851")]:
        x_ref = ex(est_ref)
        parts.append(
            f'<line x1="{x_ref:.1f}" y1="{y_top}" x2="{x_ref:.1f}" y2="{y_bot}" '
            f'stroke="#F59E0B" stroke-width="1.2" stroke-dasharray="4 3" opacity="0.85"/>'
        )
        anchor = "start" if est_ref == 1851 else "end"
        offset = 3 if est_ref == 1851 else -3
        parts.append(
            f'<text x="{x_ref+offset:.1f}" y="{y_top+10}" fill="#F59E0B" '
            f'font-size="8" font-weight="500" text-anchor="{anchor}">{label_ref}</text>'
        )

    # ── Dibujar tramos por ítem ──────────────────────────────────────────

    # Troncal: línea completa siempre (100%)
    y = NIVELES_Y["troncal"]
    c = COLORES["troncal"]
    parts.append(f'<line x1="{X0}" y1="{y}" x2="{X1}" y2="{y}" '
                 f'stroke="{c}" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<text x="{X0-4}" y="{y+3}" text-anchor="end" '
                 f'fill="{c}" font-size="8">{LABELS["troncal"]}</text>')
    parts.append(f'<text x="{X1+4}" y="{y+3}" text-anchor="start" '
                 f'fill="{c}" font-size="8">100%</text>')

    # Sensitiva: tramos activos por frente (uno por frente, el más reciente)
    y  = NIVELES_Y["sensitiva"]
    c  = COLORES["sensitiva"]
    total_est_s = 0
    if not df_05_sens.empty:
        for _, row in df_05_sens.iterrows():
            d, h = int(row["estacion_desde"]), int(row["estacion_hasta"])
            x0s, x1s = sorted([ex(d), ex(h)])
            if x1s - x0s < 1.5:
                parts.append(f'<circle cx="{(x0s+x1s)/2:.1f}" cy="{y}" r="2.5" fill="{c}"/>')
            else:
                parts.append(
                    f'<line x1="{x0s:.1f}" y1="{y}" x2="{x1s:.1f}" y2="{y}" '
                    f'stroke="{c}" stroke-width="4" stroke-linecap="round" opacity="0.9"/>'
                )
            total_est_s += abs(h - d)
    # Porcentaje: usar el valor real de met_05 si viene, si no calcular desde estaciones
    pct_s_total = pct_s_real if pct_s_real is not None else min(total_est_s / TOTAL_EST_CV005 * 100, 100.0)
    parts.append(f'<text x="{X0-4}" y="{y+3}" text-anchor="end" '
                 f'fill="{c}" font-size="8">{LABELS["sensitiva"]}</text>')
    parts.append(f'<text x="{X1+4}" y="{y+3}" text-anchor="start" '
                 f'fill="{c}" font-size="8">{pct_s_total:.1f}%</text>')

    # Ítems de avance físico desde df_af
    for item_key in ["fo_posicionada", "fo_retirada", "clips", "tejido"]:
        y  = NIVELES_Y[item_key]
        c  = COLORES[item_key]
        iv = ITEMS_AVANCE_FISICO[item_key]
        total_est = 0
        if not df_af.empty:
            sub = df_af[df_af["item"] == item_key]
            for _, row in sub.iterrows():
                d, h = int(row["est_desde"]), int(row["est_hasta"])
                x0s, x1s = sorted([ex(d), ex(h)])
                if x1s - x0s < 1.5:   # segmento muy pequeño → punto
                    parts.append(
                        f'<circle cx="{(x0s+x1s)/2:.1f}" cy="{y}" r="2.5" fill="{c}"/>'
                    )
                else:
                    parts.append(
                        f'<line x1="{x0s:.1f}" y1="{y}" x2="{x1s:.1f}" y2="{y}" '
                        f'stroke="{c}" stroke-width="4" stroke-linecap="round" opacity="0.9"/>'
                    )
                total_est += abs(h - d)
        pct = min(total_est / TOTAL_EST_CV005 * 100, 100.0)
        parts.append(f'<text x="{X0-4}" y="{y+3}" text-anchor="end" '
                     f'fill="{c}" font-size="8">{LABELS[item_key]}</text>')
        parts.append(f'<text x="{X1+4}" y="{y+3}" text-anchor="start" '
                     f'fill="{c}" font-size="8">{pct:.1f}%</text>')

    parts.append('</svg>')
    return "".join(parts)


# Obtener tramos de sensitiva CV005 para el gráfico (todos los registros, no solo el más reciente)
def leer_todos_tramos_sensitiva_cv005(df):
    """
    Retorna el tramo activo (más reciente) por cada frente de CV005
    para dibujar en el gráfico SVG. Evita sumar registros históricos.
    """
    if df.empty:
        return pd.DataFrame()
    sub = df[df["nivel"].astype(int) == 5].copy()
    if sub.empty:
        return pd.DataFrame()
    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at", ascending=False)
    if "frente" in sub.columns:
        # Un solo registro por frente (el más reciente)
        return sub.drop_duplicates(subset=["frente"], keep="first")
    # Si no hay columna frente, tomar solo el más reciente
    return sub.head(1)


df_05_sens_tramos = leer_todos_tramos_sensitiva_cv005(df_05)

# Solo barras de resumen en la card principal (gráfico va en pestaña detalle)
af_html = """<div style="background:rgba(255,255,255,0.02);border:0.5px solid rgba(255,255,255,0.06);
            border-radius:10px;padding:12px 14px;margin-top:8px">
  <div style="font-size:9px;text-transform:uppercase;letter-spacing:.8px;
              color:rgba(255,255,255,0.3);margin-bottom:10px">Avance físico instalación</div>"""
for ik, iv in ITEMS_AVANCE_FISICO.items():
    datos = av_fis.get(ik, {"est": 0, "pct": 0.0})
    pct   = datos["pct"]
    est   = datos.get("est", 0)
    af_html += f"""
  <div style="margin-bottom:7px">
    <div style="display:flex;justify-content:space-between;margin-bottom:2px">
      <span style="font-size:10px;color:rgba(255,255,255,0.5)">{iv['label']}</span>
      <span style="font-size:10px;font-weight:500;color:{iv['color']}">{pct:.1f}%</span>
    </div>
    <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:5px;overflow:hidden">
      <div style="width:{min(pct,100):.1f}%;background:{iv['color']};height:100%;border-radius:99px"></div>
    </div>
    <div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:1px">{est:,} est de {TOTAL_EST_CV005:,}</div>
  </div>"""
af_html += "</div>"

render_card(c1, "CV005", met_05, False, frentes_05, av_fis_extra=af_html)
render_card(c2, "CV006", met_06, False, frentes_06)
cv007_completada = met_07["troncal_completa"] and met_07["pct_s"] >= 99.9
render_card(c3, "CV007", met_07, cv007_completada, frentes_07)

# ============================================================
# HISTORIAL
# ============================================================
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
            text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
  Historial de registros de campo
</div>
""", unsafe_allow_html=True)

df_hist = leer_historial(limit=50)
if not df_hist.empty:
    df_view = pd.DataFrame()
    df_view["Correa"]      = df_hist["correa_id"]
    df_view["Frente"]      = df_hist["frente"] if "frente" in df_hist.columns else "—"
    df_view["Tipo evento"] = df_hist["tipo_evento"] if "tipo_evento" in df_hist.columns else "—"
    df_view["Fibra"]       = df_hist["nivel"].apply(lambda x: NIVELES.get(int(x), str(x)))
    df_view["Operador"]    = df_hist["operador"] if "operador" in df_hist.columns else "—"

    def fmt_tramo(row):
        d = row.get("estacion_desde", "—")
        h = row.get("estacion_hasta", "—")
        if row.get("correa_id") == "CV006":
            d = MAPEO_NUM_A_LETRA.get(int(d) if str(d).lstrip("-").isdigit() else 0, str(d))
        return f"{d} → {h}"

    df_view["Tramo"]       = df_hist.apply(fmt_tramo, axis=1)
    df_view["Observación"] = df_hist["nota"].fillna("") if "nota" in df_hist.columns else ""
    if "created_at" in df_hist.columns:
        df_hist["created_at_dt"] = pd.to_datetime(df_hist["created_at"], utc=True).dt.tz_convert("America/Santiago")
        df_view["Fecha"] = df_hist["created_at_dt"].dt.strftime("%d-%m-%Y %H:%M")
    else:
        df_view["Fecha"] = "—"

    st.dataframe(
        df_view[["Correa","Frente","Tipo evento","Fibra","Tramo","Operador","Observación","Fecha"]],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("Sin registros en la base de datos aún.")

# ============================================================
# FORMULARIOS DE INGRESO
# ============================================================
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
            text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
  Ingreso de datos
</div>
""", unsafe_allow_html=True)

ftab05, ftab06, ftab07, ftab_pdf, ftab_esquema, ftab_cv005_detalle, ftab_cortes = st.tabs(
    ["➕ CV005", "➕ CV006", "➕ CV007", "📄 Reporte PDF", "🔧 Esquema de correas", "📊 Detalle CV005", "📈 Análisis de cortes"]
)

# ── CV005 ─────────────────────────────────────────────────────
with ftab05:
    col_f, col_info = st.columns([2, 1])
    with col_f:
        with st.form(key="form_CV005"):
            fa, fb = st.columns(2)
            with fa:
                op_05 = st.text_input("Operador", key="op_CV005", placeholder="Nombre")
            with fb:
                te_05 = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV005")
            fc, fd = st.columns(2)
            with fc:
                niv_05 = st.selectbox("Tipo de fibra", [0, 5],
                    format_func=lambda x: "Troncal" if x == 0 else "Sensitiva", key="niv_CV005")
            with fd:
                fr_05 = st.selectbox("Frente de trabajo",
                    ["TP1 → Centro (Est. 3823 → 2000)", "EM → Centro (Est. 1 → 2000)"],
                    key="frente_CV005")
            fk_05 = "tp1" if "TP1" in fr_05 else "em"
            fe, ff = st.columns(2)
            with fe:
                d_05 = st.number_input("Desde Est.",
                    min_value=1, max_value=3823,
                    value=3823 if fk_05 == "tp1" else 1,
                    step=1, key="d05", format="%d")
            with ff:
                h_05 = st.number_input("Hasta Est.",
                    min_value=1, max_value=3823,
                    value=2000,
                    step=1, key="h05", format="%d")
            fac_05 = FACTORES["CV005"]["troncal"] if niv_05 == 0 else FACTORES["CV005"]["sensitiva"]
            st.caption(f"📏 {abs(int(h_05)-int(d_05))} est × {fac_05:.3f} m/est = **{abs(int(h_05)-int(d_05))*fac_05:,.1f} m**")
            nota_05 = st.text_input("Observación", key="nota_CV005", placeholder="Opcional")
            if st.form_submit_button("💾 Guardar registro CV005"):
                if not op_05.strip():
                    st.error("Ingresa el operador.")
                else:
                    if guardar_registro(op_05.strip(), d_05, h_05, niv_05, nota_05, te_05, "CV005", fk_05):
                        st.success(f"✅ Guardado — CV005 / Frente {fk_05.upper()}")
                        st.rerun()

    # ── Formulario avance físico CV005 ──────────────────────────────────
    st.markdown("""
    <div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                color:rgba(255,255,255,0.35);margin-top:16px;margin-bottom:8px">
      Avance físico instalación — CV005
    </div>""", unsafe_allow_html=True)

    with st.form(key="form_av_fisico_cv005"):
        af1, af2 = st.columns(2)
        with af1:
            af_op   = st.text_input("Operador", key="af_op_cv005", placeholder="Nombre")
            af_item = st.selectbox("Ítem",
                        list(ITEMS_AVANCE_FISICO.keys()),
                        format_func=lambda x: ITEMS_AVANCE_FISICO[x]["label"],
                        key="af_item_cv005")
            af_tipo = st.selectbox("Tipo de evento", TIPOS_AVANCE_FISICO, key="af_tipo_cv005")
        with af2:
            af_desde = st.number_input("Desde Est.", min_value=1, max_value=3823,
                                        value=1, step=1, key="af_desde_cv005", format="%d")
            af_hasta = st.number_input("Hasta Est.", min_value=1, max_value=3823,
                                        value=3823, step=1, key="af_hasta_cv005", format="%d")
            af_nota  = st.text_input("Observación", key="af_nota_cv005", placeholder="Opcional")

        af_est = abs(int(af_hasta) - int(af_desde))
        af_pct = min(af_est / TOTAL_EST_CV005 * 100, 100.0)
        st.caption(f"📏 {af_est:,} est de {TOTAL_EST_CV005:,} · **{af_pct:.1f}%** de avance")

        if st.form_submit_button("💾 Guardar avance físico CV005"):
            if not af_op.strip():
                st.error("Ingresa el operador.")
            elif guardar_avance_fisico(af_op.strip(), af_item, af_tipo,
                                        af_desde, af_hasta, af_nota):
                st.success(f"✅ Guardado — {ITEMS_AVANCE_FISICO[af_item]['label']}")
                st.rerun()
    with col_info:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:14px 16px;margin-top:2px">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                      color:rgba(255,255,255,0.35);margin-bottom:10px">Referencia CV005</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);line-height:1.8">
            <span style="color:#E24B4A">●</span> Troncal: 1.547 m/est<br>
            <span style="color:#7F77DD">●</span> Sensitiva: 10.83 m/est<br><br>
            <span style="color:rgba(255,255,255,0.3)">Frente TP1</span><br>
            Est. 3823 → 2000 (decrece)<br><br>
            <span style="color:rgba(255,255,255,0.3)">Frente EM</span><br>
            Est. 1 → 2000 (crece)
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("""<div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                    color:rgba(255,255,255,0.35);margin-top:14px;margin-bottom:6px">
          Calculadora SmartVision</div>""", unsafe_allow_html=True)
        c05_fibra   = st.selectbox("Tipo de fibra", [0,5], format_func=lambda x:"Troncal" if x==0 else "Sensitiva", key="c05_fibra")
        c05_frente  = st.selectbox("Frente", ["TP1 (origen Est. 3823)","EM (origen Est. 1)"], key="c05_frente")
        c05_metros  = st.number_input("Metros SmartVision", min_value=0.0, value=0.0, step=1.0, key="c05_metros", format="%.1f")
        c05_factor  = FACTORES["CV005"]["troncal"] if c05_fibra==0 else FACTORES["CV005"]["sensitiva"]
        c05_orig    = {"TP1 (origen Est. 3823)":(3823,-1),"EM (origen Est. 1)":(1,1)}[c05_frente]
        c05_offset  = OFFSET_METROS["CV005"]["tp1"] if "TP1" in c05_frente else 0.0

        # Para TP1: SmartVision parte en 122 m → descontamos el offset antes de convertir a estaciones
        c05_metros_netos = max(c05_metros - c05_offset, 0.0)  # descuenta cabecera DTS

        if c05_metros >= c05_offset or c05_metros == 0:
            c05_est = max(EST_RANGES["CV005"]["min"], min(EST_RANGES["CV005"]["max"],
                          round(c05_orig[0] + c05_orig[1] * (c05_metros_netos / c05_factor)))) if c05_metros > 0 else c05_orig[0]
            c05_offset_txt = f"  ·  incluye {c05_offset:.0f} m de cabecera DTS" if c05_offset > 0 else ""
            st.markdown(f"""<div style="background:rgba(55,138,221,0.1);border:0.5px solid rgba(55,138,221,0.3);
                        border-radius:8px;padding:10px 12px;margin-top:4px">
              <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-bottom:3px">Estación equivalente</div>
              <div style="font-size:22px;font-weight:500;color:#378ADD">Est. {c05_est:,}</div>
              <div style="font-size:10px;color:rgba(255,255,255,0.35);margin-top:3px">
                ({c05_metros:,.1f} − {c05_offset:.0f}) m ÷ {c05_factor:.3f} = {c05_metros_netos/c05_factor:.1f} est{c05_offset_txt}
              </div></div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="background:rgba(245,158,11,0.08);border:0.5px solid rgba(245,158,11,0.3);
                        border-radius:8px;padding:10px 12px;margin-top:4px;
                        font-size:11px;color:#F59E0B">
              ⚠ Los primeros {c05_offset:.0f} m corresponden a la cabecera DTS (antes de Est. 3823)
            </div>""", unsafe_allow_html=True)

# ── CV006 ─────────────────────────────────────────────────────
with ftab06:
    col_f, col_info = st.columns([2, 1])
    with col_f:
        with st.form(key="form_CV006"):
            fa, fb = st.columns(2)
            with fa:
                op_06 = st.text_input("Operador", key="op_CV006", placeholder="Nombre")
            with fb:
                te_06 = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV006")
            fc, fd = st.columns(2)
            with fc:
                niv_06 = st.selectbox("Tipo de fibra", [0, 5],
                    format_func=lambda x: "Troncal" if x == 0 else "Sensitiva", key="niv_CV006")
            with fd:
                fr_06 = st.selectbox("Frente de trabajo",
                    ["TP1 → Centro (3B Carga → Est. 1845)", "TP2 → Centro (Est. 3526 → 1846)"],
                    key="frente_CV006")
            fk_06 = "tp1" if "TP1" in fr_06 else "tp2"
            fe, ff = st.columns(2)
            with fe:
                d_06 = st.number_input("Desde Est.",
                    min_value=-3, max_value=3526,
                    value=-3 if fk_06 == "tp1" else 3526,
                    step=1, key="d06", format="%d")
            with ff:
                h_06 = st.number_input("Hasta Est.",
                    min_value=-3, max_value=3526,
                    value=1845 if fk_06 == "tp1" else 1846,
                    step=1, key="h06", format="%d")
            fac_06 = FACTORES["CV006"]["troncal"] if niv_06 == 0 else FACTORES["CV006"]["sensitiva"]
            st.caption(f"📏 {abs(int(h_06)-int(d_06))} est × {fac_06:.3f} m/est = **{abs(int(h_06)-int(d_06))*fac_06:,.1f} m**")
            nota_06 = st.text_input("Observación", key="nota_CV006", placeholder="Opcional")
            if st.form_submit_button("💾 Guardar registro CV006"):
                if not op_06.strip():
                    st.error("Ingresa el operador.")
                elif fk_06 == "tp1" and (int(d_06) > 1845 or int(h_06) > 1845):
                    st.error("Frente TP1: estaciones deben estar entre −3 y 1845.")
                elif fk_06 == "tp2" and (int(d_06) < 1846 or int(h_06) < 1846):
                    st.error("Frente TP2: estaciones deben estar entre 1846 y 3526.")
                else:
                    if guardar_registro(op_06.strip(), d_06, h_06, niv_06, nota_06, te_06, "CV006", fk_06):
                        st.success(f"✅ Guardado — CV006 / Frente {fk_06.upper()}")
                        st.rerun()
    with col_info:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:14px 16px;margin-top:2px">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                      color:rgba(255,255,255,0.35);margin-bottom:10px">Referencia CV006</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);line-height:1.8">
            <span style="color:#E24B4A">●</span> Troncal: 1.665 m/est<br>
            <span style="color:#7F77DD">●</span> Sensitiva: 13.66 m/est<br><br>
            <span style="color:rgba(255,255,255,0.3)">Frente TP1</span><br>
            3B Carga (−3) → 1845 (crece)<br><br>
            <span style="color:rgba(255,255,255,0.3)">Frente TP2</span><br>
            Est. 3526 → 1846 (decrece)
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("""<div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                    color:rgba(255,255,255,0.35);margin-top:14px;margin-bottom:6px">
          Calculadora SmartVision</div>""", unsafe_allow_html=True)
        c06_fibra   = st.selectbox("Tipo de fibra", [0,5], format_func=lambda x:"Troncal" if x==0 else "Sensitiva", key="c06_fibra")
        c06_frente  = st.selectbox("Frente", ["TP1 (origen Est. -3)","TP2 (origen Est. 3526)"], key="c06_frente")
        c06_metros  = st.number_input("Metros SmartVision", min_value=0.0, value=0.0, step=1.0, key="c06_metros", format="%.1f")
        c06_factor  = FACTORES["CV006"]["troncal"] if c06_fibra==0 else FACTORES["CV006"]["sensitiva"]
        c06_orig    = {"TP1 (origen Est. -3)":(-3,1),"TP2 (origen Est. 3526)":(3526,-1)}[c06_frente]
        if c06_metros > 0:
            c06_est = max(EST_RANGES["CV006"]["min"], min(EST_RANGES["CV006"]["max"],
                          round(c06_orig[0] + c06_orig[1] * (c06_metros / c06_factor))))
            st.markdown(f"""<div style="background:rgba(55,138,221,0.1);border:0.5px solid rgba(55,138,221,0.3);
                        border-radius:8px;padding:10px 12px;margin-top:4px">
              <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-bottom:3px">Estación equivalente</div>
              <div style="font-size:22px;font-weight:500;color:#378ADD">Est. {c06_est:,}</div>
              <div style="font-size:10px;color:rgba(255,255,255,0.35);margin-top:3px">
                {c06_metros:,.1f} m ÷ {c06_factor:.3f} = {c06_metros/c06_factor:.1f} est
              </div></div>""", unsafe_allow_html=True)

# ── CV007 ─────────────────────────────────────────────────────
with ftab07:
    col_f, col_info = st.columns([2, 1])
    with col_f:
        with st.form(key="form_CV007"):
            fa, fb = st.columns(2)
            with fa:
                op_07 = st.text_input("Operador", key="op_CV007", placeholder="Nombre")
            with fb:
                te_07 = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV007")
            fc, fd = st.columns(2)
            with fc:
                niv_07 = st.selectbox("Tipo de fibra", [0, 5],
                    format_func=lambda x: "Troncal" if x == 0 else "Sensitiva", key="niv_CV007")
            with fd:
                st.markdown("""
                <div style="padding-top:28px;font-size:11px;color:rgba(255,255,255,0.4)">
                  Frente único · Est. 3 → 842
                </div>""", unsafe_allow_html=True)
            r = EST_RANGES["CV007"]
            fe, ff = st.columns(2)
            with fe:
                d_07 = st.number_input("Desde Est.", min_value=r["min"], max_value=r["max"], value=r["min"], step=1, key="d07", format="%d")
            with ff:
                h_07 = st.number_input("Hasta Est.", min_value=r["min"], max_value=r["max"], value=r["max"], step=1, key="h07", format="%d")
            fac_07 = FACTORES["CV007"]["troncal"] if niv_07 == 0 else FACTORES["CV007"]["sensitiva"]
            st.caption(f"📏 {abs(int(h_07)-int(d_07))} est × {fac_07:.3f} m/est = **{abs(int(h_07)-int(d_07))*fac_07:,.1f} m**")
            nota_07 = st.text_input("Observación", key="nota_CV007", placeholder="Opcional")
            if st.form_submit_button("💾 Guardar registro CV007"):
                if not op_07.strip():
                    st.error("Ingresa el operador.")
                else:
                    if guardar_registro(op_07.strip(), d_07, h_07, niv_07, nota_07, te_07, "CV007", "unico"):
                        st.success("✅ Guardado — CV007")
                        st.rerun()
    with col_info:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:14px 16px;margin-top:2px">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                      color:rgba(255,255,255,0.35);margin-bottom:10px">Referencia CV007</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);line-height:1.8">
            <span style="color:#E24B4A">●</span> Troncal: 1.595 m/est<br>
            <span style="color:#7F77DD">●</span> Sensitiva: 17.36 m/est<br><br>
            <span style="color:rgba(255,255,255,0.3)">Frente único</span><br>
            TP2 (Est. 3) → Shuttler (Est. 842)<br><br>
            <span style="color:#8dc63f">✓ 100% completada</span>
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("""<div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                    color:rgba(255,255,255,0.35);margin-top:14px;margin-bottom:6px">
          Calculadora SmartVision</div>""", unsafe_allow_html=True)
        c07_fibra   = st.selectbox("Tipo de fibra", [0,5], format_func=lambda x:"Troncal" if x==0 else "Sensitiva", key="c07_fibra")
        c07_metros  = st.number_input("Metros SmartVision", min_value=0.0, value=0.0, step=1.0, key="c07_metros", format="%.1f")
        c07_factor  = FACTORES["CV007"]["troncal"] if c07_fibra==0 else FACTORES["CV007"]["sensitiva"]
        if c07_metros > 0:
            c07_est = max(EST_RANGES["CV007"]["min"], min(EST_RANGES["CV007"]["max"],
                          round(3 + (c07_metros / c07_factor))))
            st.markdown(f"""<div style="background:rgba(55,138,221,0.1);border:0.5px solid rgba(55,138,221,0.3);
                        border-radius:8px;padding:10px 12px;margin-top:4px">
              <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-bottom:3px">Estación equivalente</div>
              <div style="font-size:22px;font-weight:500;color:#378ADD">Est. {c07_est:,}</div>
              <div style="font-size:10px;color:rgba(255,255,255,0.35);margin-top:3px">
                {c07_metros:,.1f} m ÷ {c07_factor:.3f} = {c07_metros/c07_factor:.1f} est
              </div></div>""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR — estado rápido + calculadora
# ============================================================
with st.sidebar:
    st.markdown("""
    <div style="padding:8px 0 10px">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.3px;
                  color:rgba(255,255,255,0.3);margin-bottom:3px">Panel de operación</div>
      <div style="font-size:14px;font-weight:500;color:#F0F2F5">Estado general</div>
    </div>""", unsafe_allow_html=True)

    for cid, pct_val in [("CV005", met_05["pct_s"]), ("CV006", met_06["pct_s"]), ("CV007", 100.0)]:
        color_bar = "#639922" if pct_val >= 100 else "#7F77DD"
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:8px;padding:8px 11px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;margin-bottom:5px">
            <span style="font-size:11px;font-weight:500;color:#F0F2F5">{cid}</span>
            <span style="font-size:10px;color:rgba(255,255,255,0.35)">Sensitiva {pct_val:.1f}%</span>
          </div>
          <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:4px;overflow:hidden">
            <div style="width:{min(pct_val,100):.1f}%;background:{color_bar};height:100%;border-radius:99px"></div>
          </div>
        </div>""", unsafe_allow_html=True)

# ============================================================
# PESTAÑA REPORTE PDF
# ============================================================
with ftab_pdf:
    from datetime import datetime, timezone, timedelta

    tz_stgo = timezone(timedelta(hours=-4))  # Chile Standard / Summer varies but -4 cubre horario de trabajo
    ahora   = datetime.now(tz_stgo)
    fecha_str = ahora.strftime("%d de %B de %Y")
    hora_str  = ahora.strftime("%H:%M hrs")

    # Historial para el reporte (últimos 20)
    df_rpt = leer_historial(limit=20)
    filas_hist = ""
    if not df_rpt.empty:
        if "created_at" in df_rpt.columns:
            df_rpt["created_at_dt"] = pd.to_datetime(df_rpt["created_at"], utc=True).dt.tz_convert("America/Santiago")
        for _, r in df_rpt.iterrows():
            d  = r.get("estacion_desde","—")
            h  = r.get("estacion_hasta","—")
            if r.get("correa_id") == "CV006":
                d = MAPEO_NUM_A_LETRA.get(int(d) if str(d).lstrip("-").isdigit() else 0, str(d))
            tramo = f"{d} → {h}"
            fecha_r = r["created_at_dt"].strftime("%d-%m-%Y %H:%M") if "created_at_dt" in r else "—"
            fibra_r = "Troncal" if int(r.get("nivel",5)) == 0 else "Sensitiva"
            filas_hist += f"""
            <tr>
              <td>{r.get('correa_id','—')}</td>
              <td>{r.get('frente','—')}</td>
              <td>{r.get('tipo_evento','—')}</td>
              <td>{fibra_r}</td>
              <td>{tramo}</td>
              <td>{r.get('operador','—')}</td>
              <td>{r.get('nota','')}</td>
              <td>{fecha_r}</td>
            </tr>"""

    # Barras de progreso para cada correa
    def barra_pdf(pct, color):
        w = min(pct, 100.0)
        return f"""<div style="background:#e5e7eb;border-radius:99px;height:8px;margin:3px 0 6px">
          <div style="width:{w:.1f}%;background:{color};height:8px;border-radius:99px"></div></div>"""

    pct_s_07 = 100.0

    badge_corte_05 = (
        ' <span class="badge-wip" style="background:#fef3c7;color:#d97706">⚠ Corte troncal</span>'
        if not met_05['troncal_completa'] else ''
    )
    badge_corte_06 = (
        ' <span class="badge-wip" style="background:#fef3c7;color:#d97706">⚠ Corte troncal</span>'
        if not met_06['troncal_completa'] else ''
    )
    sub_troncal_05 = '100% completa' if met_05['troncal_completa'] else 'con corte activo'
    sub_troncal_06 = '100% completa' if met_06['troncal_completa'] else 'con corte activo'
    color_t_05 = '#E24B4A' if met_05['pct_t'] >= 100 else '#f59e0b'
    color_t_06 = '#E24B4A' if met_06['pct_t'] >= 100 else '#f59e0b'

    html_reporte = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Reporte Fibra Óptica — {fecha_str}</title>
<style>
  @page {{ margin: 18mm 20mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a2e; background: #fff; font-size: 11px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start;
             border-bottom: 2px solid #1a1a2e; padding-bottom: 12px; margin-bottom: 18px; }}
  .header-left h1 {{ font-size: 16px; font-weight: 700; color: #1a1a2e; margin-bottom: 3px; }}
  .header-left p  {{ font-size: 10px; color: #6b7280; }}
  .header-right   {{ text-align: right; font-size: 10px; color: #6b7280; line-height: 1.6; }}
  .header-right strong {{ color: #1a1a2e; font-size: 12px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 18px; }}
  .kpi {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; }}
  .kpi-label {{ font-size: 9px; text-transform: uppercase; letter-spacing: .6px; color: #9ca3af; margin-bottom: 4px; }}
  .kpi-value {{ font-size: 18px; font-weight: 700; color: #1a1a2e; }}
  .kpi-sub   {{ font-size: 8.5px; color: #9ca3af; margin-top: 2px; }}
  .section-title {{ font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px;
                    color: #6b7280; margin: 16px 0 8px; border-bottom: 1px solid #f3f4f6; padding-bottom: 4px; }}
  .correa-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-bottom: 16px; }}
  .correa-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
  .correa-name {{ font-size: 13px; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; }}
  .badge-wip  {{ display:inline-block; font-size:8px; padding:1px 7px; border-radius:99px;
                 background:#dbeafe; color:#2563eb; font-weight:600; margin-left:6px; }}
  .badge-ok   {{ display:inline-block; font-size:8px; padding:1px 7px; border-radius:99px;
                 background:#dcfce7; color:#16a34a; font-weight:600; margin-left:6px; }}
  .metric-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 10px; }}
  .metric     {{ background: #f9fafb; border-radius: 6px; padding: 7px 9px; }}
  .metric-lbl {{ font-size: 8px; text-transform: uppercase; color: #9ca3af; margin-bottom: 2px; }}
  .metric-val {{ font-size: 13px; font-weight: 700; color: #1a1a2e; }}
  .metric-sub {{ font-size: 8px; color: #9ca3af; }}
  .bar-label  {{ display: flex; justify-content: space-between; font-size: 9px; color: #6b7280; }}
  .frente-row {{ display: flex; justify-content: space-between; font-size: 9px;
                 color: #6b7280; padding: 2px 0; border-top: 1px solid #f3f4f6; margin-top: 4px; }}
  table       {{ width: 100%; border-collapse: collapse; font-size: 9px; }}
  th          {{ background: #f3f4f6; text-align: left; padding: 5px 7px; font-weight: 600;
                 text-transform: uppercase; letter-spacing: .4px; color: #6b7280; border-bottom: 1px solid #e5e7eb; }}
  td          {{ padding: 5px 7px; border-bottom: 1px solid #f3f4f6; color: #374151; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  .footer     {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #e5e7eb;
                 font-size: 8.5px; color: #9ca3af; display: flex; justify-content: space-between; }}
  @media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>Sistema de Monitoreo de Polines — Fibra Óptica</h1>
    <p>Centro de Telemetría Térmica Avanzada &nbsp;·&nbsp; Reporte de avance</p>
  </div>
  <div class="header-right">
    <strong>{fecha_str}</strong><br>
    {hora_str}<br>
    Generado automáticamente
  </div>
</div>

<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">Troncal desplegada</div>
    <div class="kpi-value">{total_t:,.0f} m</div>
    <div class="kpi-sub">CV005: {met_05['metros_t']:,.0f} · CV006: {met_06['metros_t']:,.0f} · CV007: {met_07['metros_t']:,.0f}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Sensitiva desplegada</div>
    <div class="kpi-value">{total_s:,.0f} m</div>
    <div class="kpi-sub">CV005: {met_05['metros_s']:,.0f} · CV006: {met_06['metros_s']:,.0f} · CV007: {met_07['metros_s']:,.0f}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Troncal completada</div>
    <div class="kpi-value">{n_ok} / 3</div>
    <div class="kpi-sub">{sub_ok}{sub_corte}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Cobertura sensitiva global</div>
    <div class="kpi-value">{pct_global:.1f}%</div>
    <div class="kpi-sub">{total_s:,.0f} m de ~{total_s_pos:,.0f} m</div>
  </div>
</div>

<div class="section-title">Estado por correa</div>
<div class="correa-grid">

  <div class="correa-card">
    <div class="correa-name">CV005 <span class="badge-wip">En progreso</span>{badge_corte_05}</div>
    <div class="metric-row">
      <div class="metric"><div class="metric-lbl">Troncal</div>
        <div class="metric-val">{met_05['metros_t']:,.0f} m</div>
        <div class="metric-sub">{sub_troncal_05}</div></div>
      <div class="metric"><div class="metric-lbl">Sensitiva</div>
        <div class="metric-val">{met_05['metros_s']:,.0f} m</div>
        <div class="metric-sub">de {met_05['total_s']:,.0f} m</div></div>
    </div>
    <div class="bar-label"><span>Troncal</span><span>{met_05['pct_t']:.1f}%</span></div>
    {barra_pdf(met_05['pct_t'], color_t_05)}
    <div class="bar-label"><span>Sensitiva</span><span>{met_05['pct_s']:.1f}%</span></div>
    {barra_pdf(met_05['pct_s'], '#7F77DD')}
    <div class="frente-row"><span>Frente TP1</span><span>Est. 3823 → 2000</span></div>
    <div class="frente-row"><span>Frente EM</span><span>Est. 1 → 2000</span></div>
  </div>

  <div class="correa-card">
    <div class="correa-name">CV006 <span class="badge-wip">En progreso</span>{badge_corte_06}</div>
    <div class="metric-row">
      <div class="metric"><div class="metric-lbl">Troncal</div>
        <div class="metric-val">{met_06['metros_t']:,.0f} m</div>
        <div class="metric-sub">{sub_troncal_06}</div></div>
      <div class="metric"><div class="metric-lbl">Sensitiva</div>
        <div class="metric-val">{met_06['metros_s']:,.0f} m</div>
        <div class="metric-sub">de {met_06['total_s']:,.0f} m</div></div>
    </div>
    <div class="bar-label"><span>Troncal</span><span>{met_06['pct_t']:.1f}%</span></div>
    {barra_pdf(met_06['pct_t'], color_t_06)}
    <div class="bar-label"><span>Sensitiva</span><span>{met_06['pct_s']:.1f}%</span></div>
    {barra_pdf(met_06['pct_s'], '#7F77DD')}
    <div class="frente-row"><span>Frente TP1</span><span>3B Carga → Est. 1845</span></div>
    <div class="frente-row"><span>Frente TP2</span><span>Est. 3526 → 1846</span></div>
  </div>

  <div class="correa-card" style="border-color:#bbf7d0">
    <div class="correa-name">CV007 <span class="badge-ok">100% completada</span></div>
    <div class="metric-row">
      <div class="metric"><div class="metric-lbl">Troncal</div>
        <div class="metric-val">{met_07['metros_t']:,.0f} m</div>
        <div class="metric-sub">100% completa</div></div>
      <div class="metric"><div class="metric-lbl">Sensitiva</div>
        <div class="metric-val">{met_07['metros_s']:,.0f} m</div>
        <div class="metric-sub">de {met_07['total_s']:,.0f} m</div></div>
    </div>
    <div class="bar-label"><span>Troncal</span><span>100.0%</span></div>
    {barra_pdf(100, '#E24B4A')}
    <div class="bar-label"><span>Sensitiva</span><span>100.0%</span></div>
    {barra_pdf(100, '#16a34a')}
    <div class="frente-row"><span>Frente único</span><span>Est. 3 → 842</span></div>
  </div>

</div>

<div class="section-title">Historial de registros de campo (últimos 20 eventos)</div>
<table>
  <thead>
    <tr><th>Correa</th><th>Frente</th><th>Tipo evento</th><th>Fibra</th>
        <th>Tramo</th><th>Operador</th><th>Observación</th><th>Fecha</th></tr>
  </thead>
  <tbody>
    {filas_hist if filas_hist else '<tr><td colspan="8" style="text-align:center;color:#9ca3af">Sin registros</td></tr>'}
  </tbody>
</table>

<div class="footer">
  <span>Sistema de Monitoreo de Polines — Fibra Óptica &nbsp;·&nbsp; Centro de Telemetría Térmica Avanzada</span>
  <span>Generado el {fecha_str} a las {hora_str}</span>
</div>

<script>
  window.onload = function() {{
    // Auto-open print dialog after short delay
  }};
</script>
</body>
</html>"""

    st.markdown("""
    <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                border-radius:10px;padding:16px 18px;margin-bottom:14px">
      <div style="font-size:13px;font-weight:500;color:#F0F2F5;margin-bottom:4px">Reporte de avance</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.4)">
        Genera un reporte PDF con el estado actual de las tres correas y el historial de registros.
        Al hacer clic se abre el reporte en una nueva pestaña — usa <strong style="color:rgba(255,255,255,0.7)">
        Ctrl+P / Cmd+P</strong> o el botón de imprimir del navegador y selecciona <strong
        style="color:rgba(255,255,255,0.7)">Guardar como PDF</strong>.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Encode HTML to base64 for download link
    import base64
    html_bytes   = html_reporte.encode("utf-8")
    html_b64     = base64.b64encode(html_bytes).decode()
    nombre_pdf   = f"Reporte_FibraOptica_{ahora.strftime('%Y%m%d_%H%M')}.html"

    st.markdown(f"""
    <a href="data:text/html;base64,{html_b64}" download="{nombre_pdf}"
       style="display:inline-flex;align-items:center;gap:8px;
              background:rgba(55,138,221,0.15);border:0.5px solid rgba(55,138,221,0.4);
              color:#378ADD;border-radius:8px;padding:10px 20px;font-size:13px;
              font-weight:500;text-decoration:none;margin-bottom:14px">
      ⬇️ Descargar reporte HTML → abrir → Ctrl+P → Guardar como PDF
    </a>
    """, unsafe_allow_html=True)

    # Preview
    st.markdown("""
    <div style="font-size:10px;text-transform:uppercase;letter-spacing:.8px;
                color:rgba(255,255,255,0.35);margin-bottom:8px">Vista previa del reporte</div>
    """, unsafe_allow_html=True)
    st.components.v1.html(html_reporte, height=700, scrolling=True)

# ============================================================
# PESTAÑA ESQUEMA DE CORREAS (correa transportadora real)
def generar_svg_correa_simple(x0, y0, x1, y1, label_izq, est_izq, label_der, est_der,
                                pct_t, color_t, pct_s, color_s, lado_s, troncal_label_pos="left"):
    """
    Dibuja UNA correa transportadora individual (tambores + tramo carga/retorno + carriles).
    Retorna lista de partes SVG. (x0,y0)=tambor izquierdo, (x1,y1)=tambor derecho.
    lado_s: 'izq' o 'der' — desde qué extremo crece el relleno de sensitiva.
    """
    parts = []
    r_tambor = 22
    largo = x1 - x0

    parts.append(f'<circle cx="{x0}" cy="{y0}" r="{r_tambor}" fill="none" stroke="#9CA3AF" stroke-width="3"/>')
    parts.append(f'<circle cx="{x0}" cy="{y0}" r="7" fill="#9CA3AF" opacity="0.6"/>')
    parts.append(f'<circle cx="{x1}" cy="{y1}" r="{r_tambor}" fill="none" stroke="#9CA3AF" stroke-width="3"/>')
    parts.append(f'<circle cx="{x1}" cy="{y1}" r="7" fill="#9CA3AF" opacity="0.6"/>')

    parts.append(f'<line x1="{x0}" y1="{y0-r_tambor}" x2="{x1}" y2="{y1-r_tambor}" stroke="#D1D5DB" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<line x1="{x0}" y1="{y0+r_tambor}" x2="{x1}" y2="{y1+r_tambor}" stroke="#6B7280" stroke-width="3" stroke-linecap="round" opacity="0.6"/>')
    parts.append(f'<path d="M{x0},{y0-r_tambor} A{r_tambor},{r_tambor} 0 0,0 {x0},{y0+r_tambor}" fill="none" stroke="#D1D5DB" stroke-width="4"/>')
    parts.append(f'<path d="M{x1},{y1-r_tambor} A{r_tambor},{r_tambor} 0 0,1 {x1},{y1+r_tambor}" fill="none" stroke="#D1D5DB" stroke-width="4"/>')

    for i in range(1, 4):
        px = x0 + (largo / 4) * i
        py = y0 + ((y1 - y0) / 4) * i
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#9CA3AF" opacity="0.55"/>')

    y_troncal = min(y0, y1) - r_tambor - 26
    y_sens    = min(y0, y1) - r_tambor - 10

    label_x = x0 - 40 if troncal_label_pos == "left" else x1 + 40
    anchor  = "end" if troncal_label_pos == "left" else "start"

    parts.append(f'<text x="{label_x}" y="{y_troncal+4}" text-anchor="{anchor}" fill="#9CA3AF" font-size="10">Troncal</text>')
    parts.append(f'<line x1="{x0}" y1="{y_troncal+8}" x2="{x1}" y2="{y_troncal+8}" stroke="#4B5563" stroke-width="1.5" opacity="0.5"/>')
    ancho_t = largo * (min(pct_t,100.0) / 100.0)
    parts.append(f'<rect x="{x0}" y="{y_troncal+4}" width="{ancho_t:.1f}" height="7" rx="3.5" fill="{color_t}" opacity="0.9"/>')

    parts.append(f'<text x="{label_x}" y="{y_sens+4}" text-anchor="{anchor}" fill="#9CA3AF" font-size="10">Sensitiva</text>')
    parts.append(f'<line x1="{x0}" y1="{y_sens+8}" x2="{x1}" y2="{y_sens+8}" stroke="#4B5563" stroke-width="1.5" opacity="0.5"/>')
    ancho_s = largo * (min(pct_s,100.0) / 100.0)
    sx = x0 if lado_s == "izq" else (x1 - ancho_s)
    parts.append(f'<rect x="{sx:.1f}" y="{y_sens+4}" width="{ancho_s:.1f}" height="7" rx="3.5" fill="{color_s}" opacity="0.95"/>')

    y_label_ext = max(y0, y1) + r_tambor + 28
    parts.append(f'<text x="{x0}" y="{y_label_ext}" text-anchor="middle" fill="#F0F2F5" font-size="13" font-weight="500">{label_izq}</text>')
    parts.append(f'<text x="{x0}" y="{y_label_ext+14}" text-anchor="middle" fill="#9CA3AF" font-size="10">{est_izq}</text>')
    parts.append(f'<text x="{x1}" y="{y_label_ext}" text-anchor="middle" fill="#F0F2F5" font-size="13" font-weight="500">{label_der}</text>')
    parts.append(f'<text x="{x1}" y="{y_label_ext+14}" text-anchor="middle" fill="#9CA3AF" font-size="10">{est_der}</text>')

    return parts, y_label_ext + 14


def generar_svg_correa_doble(correa_id, met, frente_a, frente_b):
    """
    Dibuja DOS correas independientes apiladas verticalmente, cada una llegando al centro.
    frente_a / frente_b: dicts con keys label_origen, est_origen, label_centro, est_centro,
                          pct_s, color_s, lado_s (izq=crece desde origen, der=crece desde centro)
    """
    w = 680
    parts = [f'<svg width="100%" viewBox="0 0 {w} 340" role="img" aria-label="Esquema dos correas transportadoras {correa_id}">']
    parts.append(f'<text x="{w/2}" y="24" text-anchor="middle" fill="#F0F2F5" font-size="15" font-weight="500">{correa_id}</text>')

    pct_t = min(met["pct_t"], 100.0)
    color_t = "#E24B4A" if met["pct_t"] >= 100 else "#f59e0b"

    # Correa A (arriba): origen -> centro
    sub_a, _ = generar_svg_correa_simple(
        80, 110, 330, 110,
        frente_a["label_origen"], frente_a["est_origen"],
        frente_a["label_centro"], frente_a["est_centro"],
        pct_t, color_t, frente_a["pct_s"], frente_a["color_s"], frente_a["lado_s"],
        troncal_label_pos="left",
    )
    parts.extend(sub_a)

    # Correa B (abajo): centro -> origen
    sub_b, _ = generar_svg_correa_simple(
        350, 230, 600, 230,
        frente_b["label_centro"], frente_b["est_centro"],
        frente_b["label_origen"], frente_b["est_origen"],
        pct_t, color_t, frente_b["pct_s"], frente_b["color_s"], frente_b["lado_s"],
        troncal_label_pos="right",
    )
    parts.extend(sub_b)

    sub_t = "100% completa" if met["troncal_completa"] else "⚠ con corte activo"
    parts.append(f'<text x="{w/2}" y="320" text-anchor="middle" fill="#9CA3AF" font-size="11">Troncal: {met["metros_t"]:,.0f} m · {sub_t} · {met["factor_t"]:.2f} m/est</text>')
    parts.append(f'<text x="{w/2}" y="335" text-anchor="middle" fill="#9CA3AF" font-size="11">{frente_a["detalle"]}  ·  {frente_b["detalle"]}</text>')

    parts.append('</svg>')
    return "".join(parts)


def generar_svg_correa_unica(correa_id, met, label_izq, est_izq, label_der, est_der, pct_s, color_s, detalle_s):
    """Dibuja una sola correa (para CV007)."""
    w = 680
    parts = [f'<svg width="100%" viewBox="0 0 {w} 220" role="img" aria-label="Esquema correa transportadora {correa_id}">']
    parts.append(f'<text x="{w/2}" y="24" text-anchor="middle" fill="#F0F2F5" font-size="15" font-weight="500">{correa_id}</text>')

    pct_t = min(met["pct_t"], 100.0)
    color_t = "#E24B4A" if met["pct_t"] >= 100 else "#f59e0b"

    sub, y_end = generar_svg_correa_simple(
        90, 130, 590, 130,
        label_izq, est_izq, label_der, est_der,
        pct_t, color_t, pct_s, color_s, "izq",
        troncal_label_pos="left",
    )
    parts.extend(sub)

    sub_t = "100% completa" if met["troncal_completa"] else "⚠ con corte activo"
    parts.append(f'<text x="{w/2}" y="{y_end+26}" text-anchor="middle" fill="#9CA3AF" font-size="11">Troncal: {met["metros_t"]:,.0f} m · {sub_t} · {met["factor_t"]:.2f} m/est</text>')
    parts.append(f'<text x="{w/2}" y="{y_end+42}" text-anchor="middle" fill="#9CA3AF" font-size="11">{detalle_s}</text>')

    parts.append('</svg>')
    return "".join(parts)


with ftab_esquema:
    st.markdown("""
    <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                border-radius:10px;padding:14px 16px;margin-bottom:16px">
      <div style="font-size:13px;font-weight:500;color:#F0F2F5;margin-bottom:4px">Distribución física de fibra</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.4)">
        Vista lateral de cada correa transportadora con sus tambores motrices, mostrando el avance
        real de fibra troncal y sensitiva en carriles separados. CV005 y CV006 son correas dobles
        que llegan al centro desde ambos extremos.
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    .esquema-card { background:rgba(255,255,255,0.03); border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:12px; padding:12px 8px; margin-bottom:18px; }
    </style>
    """, unsafe_allow_html=True)

    # ── CV005 (correa doble) ──
    tp1_d, tp1_h = obtener_tramo_activo(df_05, 5, "tp1")
    em_d,  em_h  = obtener_tramo_activo(df_05, 5, "em")
    pct_tp1_05 = min(abs((tp1_d if tp1_d is not None else 3823) - (tp1_h or 2000)) / (3823-2000) * 100, 100) if tp1_d else 0
    pct_em_05  = min(abs((em_d if em_d is not None else 1) - (em_h or 2000)) / (2000-1) * 100, 100) if em_d else 0

    frente_a_05 = {
        "label_origen": "TP1", "est_origen": "Est. 3823",
        "label_centro": "Centro", "est_centro": "Est. 2000",
        "pct_s": pct_tp1_05, "color_s": "#7F77DD", "lado_s": "izq",
        "detalle": f"Sensitiva TP1: Est. {tp1_d if tp1_d is not None else 3823} → {tp1_h if tp1_h is not None else 2000}",
    }
    frente_b_05 = {
        "label_origen": "EM", "est_origen": "Est. 1",
        "label_centro": "Centro", "est_centro": "Est. 2000",
        "pct_s": pct_em_05, "color_s": "#1D9E75", "lado_s": "der",
        "detalle": f"Sensitiva EM: Est. {em_d if em_d is not None else 1} → {em_h if em_h is not None else 2000}",
    }
    svg_05 = generar_svg_correa_doble("CV005", met_05, frente_a_05, frente_b_05)
    st.markdown(f'<div class="esquema-card">{svg_05}</div>', unsafe_allow_html=True)

    # ── CV006 (correa doble) ──
    t1d, t1h = obtener_tramo_activo(df_06, 5, "tp1")
    t2d, t2h = obtener_tramo_activo(df_06, 5, "tp2")
    pct_tp1_06 = min(abs((t1d if t1d is not None else -3) - (t1h or 1845)) / (1845-(-3)) * 100, 100) if t1d is not None else 0
    pct_tp2_06 = min(abs((t2d if t2d is not None else 3526) - (t2h or 1846)) / (3526-1846) * 100, 100) if t2d else 0
    t1d_label = MAPEO_NUM_A_LETRA.get(t1d, str(t1d)) if t1d is not None else "3B Carga"

    frente_a_06 = {
        "label_origen": "TP1", "est_origen": "3B Carga",
        "label_centro": "Centro", "est_centro": "Est. 1845",
        "pct_s": pct_tp1_06, "color_s": "#7F77DD", "lado_s": "izq",
        "detalle": f"Sensitiva TP1: {t1d_label} → {t1h if t1h is not None else 1845}",
    }
    frente_b_06 = {
        "label_origen": "TP2", "est_origen": "Est. 3526",
        "label_centro": "Centro", "est_centro": "Est. 1846",
        "pct_s": pct_tp2_06, "color_s": "#1D9E75", "lado_s": "der",
        "detalle": f"Sensitiva TP2: Est. {t2d if t2d is not None else 3526} → {t2h if t2h is not None else 1846}",
    }
    svg_06 = generar_svg_correa_doble("CV006", met_06, frente_a_06, frente_b_06)
    st.markdown(f'<div class="esquema-card">{svg_06}</div>', unsafe_allow_html=True)

    # ── CV007 (correa única) ──
    u_d, u_h = obtener_tramo_activo(df_07, 5, "unico")
    pct_unico_07 = min(abs((u_d if u_d is not None else 3) - (u_h or 842)) / (842-3) * 100, 100) if u_d else 100
    detalle_07 = f"Frente único: Est. {u_d if u_d is not None else 3} → {u_h if u_h is not None else 842}"

    svg_07 = generar_svg_correa_unica(
        "CV007", met_07, "TP2", "Est. 3", "Shuttler", "Est. 842",
        pct_unico_07, "#1D9E75", detalle_07
    )
    st.markdown(f'<div class="esquema-card">{svg_07}</div>', unsafe_allow_html=True)

# ============================================================
# PESTAÑA DETALLE CV005
# ============================================================
with ftab_cv005_detalle:

    st.markdown("""
    <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:0 0 14px">
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
                    color:rgba(255,255,255,0.3);margin-bottom:4px">Vista detallada</div>
        <div style="font-size:17px;font-weight:500;color:#F0F2F5">
          CV005 — Instalación de fibra óptica
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPIs de CV005 ───────────────────────────────────────────────────
    d1, d2, d3, d4 = st.columns(4)
    pct_s_05 = met_05["pct_s"]
    pct_t_05 = met_05["pct_t"]
    av_global_05 = (
        av_fis.get("fo_posicionada", {}).get("pct", 0) +
        av_fis.get("fo_retirada",    {}).get("pct", 0) +
        av_fis.get("clips",          {}).get("pct", 0) +
        av_fis.get("tejido",         {}).get("pct", 0)
    ) / 4

    with d1:
        st.markdown(kpi("Sensitiva desplegada",
            f"{met_05['metros_s']:,.0f} m",
            f"{pct_s_05:.1f}% de {met_05['total_s']:,.0f} m totales",
            "#7F77DD"), unsafe_allow_html=True)
    with d2:
        st.markdown(kpi("Troncal",
            f"{met_05['metros_t']:,.0f} m",
            "100% completa" if met_05["troncal_completa"] else "⚠ Corte activo",
            "#E24B4A"), unsafe_allow_html=True)
    with d3:
        est_tejida = av_fis.get("tejido", {}).get("est", 0)
        pct_tejida = av_fis.get("tejido", {}).get("pct", 0.0)
        st.markdown(kpi("FO Tejida",
            f"{est_tejida:,} est",
            f"{pct_tejida:.1f}% de {TOTAL_EST_CV005:,} estaciones",
            "#34D399"), unsafe_allow_html=True)
    with d4:
        st.markdown(kpi("Avance global instalación",
            f"{av_global_05:.1f}%",
            "Promedio FO Pos. · Ret. · Clips · Tejida",
            "#BA7517"), unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Gráfico SVG de tramos ────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
      Distribución de tramos por ítem
    </div>""", unsafe_allow_html=True)

    svg_af_detalle = generar_svg_avance_fisico(df_af, df_05_sens_tramos, pct_s_real=met_05["pct_s"])
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                border-radius:12px;padding:16px 12px">
      {svg_af_detalle}
    </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Barras detalladas por ítem ───────────────────────────────────────
    st.markdown("""
    <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
      Avance por ítem
    </div>""", unsafe_allow_html=True)

    # Sensitiva primero
    col_items = st.columns(2)
    items_lista = [
        ("sensitiva_fo", "Fibra Óptica Sensitiva", "#7F77DD",
         met_05["metros_s"], met_05["total_s"] / FACTORES["CV005"]["sensitiva"],
         pct_s_05,
         f"{met_05['metros_s']:,.0f} m · {met_05['total_s']:,.0f} m totales · {FACTORES['CV005']['sensitiva']:.2f} m/est"),
    ]
    for ik, iv in ITEMS_AVANCE_FISICO.items():
        datos = av_fis.get(ik, {"est": 0, "pct": 0.0})
        items_lista.append((
            ik, iv["label"], iv["color"],
            datos.get("est", 0), TOTAL_EST_CV005,
            datos.get("pct", 0.0),
            f"{datos.get('est',0):,} est · {TOTAL_EST_CV005:,} est totales",
        ))

    for i, (ik, label, color, val, total, pct, sub) in enumerate(items_lista):
        with col_items[i % 2]:
            pct_w = min(pct, 100.0)
            val_fmt = f"{val:,.0f} m" if ik == "sensitiva_fo" else f"{val:,} est"
            st.markdown(f"""
            <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                        border-radius:10px;padding:13px 15px;margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <span style="font-size:12px;font-weight:500;color:#F0F2F5">{label}</span>
                <span style="font-size:13px;font-weight:500;color:{color}">{pct:.1f}%</span>
              </div>
              <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:8px;overflow:hidden;margin-bottom:6px">
                <div style="width:{pct_w:.1f}%;background:{color};height:100%;border-radius:99px;
                            transition:width .4s ease"></div>
              </div>
              <div style="display:flex;justify-content:space-between">
                <span style="font-size:10px;color:rgba(255,255,255,0.4)">{val_fmt}</span>
                <span style="font-size:10px;color:rgba(255,255,255,0.3)">{sub}</span>
              </div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Historial de registros CV005 ─────────────────────────────────────
    st.markdown("""
    <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
      Historial de registros CV005
    </div>""", unsafe_allow_html=True)

    # Combinar eventos de fibra + avance físico
    rows_hist = []
    if not df_05.empty and "created_at" in df_05.columns:
        df_05_hist = df_05.copy()
        df_05_hist["created_at_dt"] = pd.to_datetime(
            df_05_hist["created_at"], utc=True).dt.tz_convert("America/Santiago")
        for _, r in df_05_hist.sort_values("created_at_dt", ascending=False).iterrows():
            rows_hist.append({
                "Tipo": "Fibra óptica",
                "Ítem": NIVELES.get(int(r.get("nivel", 5)), str(r.get("nivel", ""))),
                "Frente": r.get("frente", "—"),
                "Evento": r.get("tipo_evento", "—"),
                "Tramo": f"Est. {r.get('estacion_desde','?')} → {r.get('estacion_hasta','?')}",
                "Operador": r.get("operador", "—"),
                "Observación": r.get("nota", ""),
                "Fecha": r["created_at_dt"].strftime("%d-%m-%Y %H:%M"),
            })

    if not df_af.empty and "created_at" in df_af.columns:
        df_af_hist = df_af.copy()
        df_af_hist["created_at_dt"] = pd.to_datetime(
            df_af_hist["created_at"], utc=True).dt.tz_convert("America/Santiago")
        for _, r in df_af_hist.sort_values("created_at_dt", ascending=False).iterrows():
            rows_hist.append({
                "Tipo": "Avance físico",
                "Ítem": ITEMS_AVANCE_FISICO.get(r.get("item",""), {}).get("label", r.get("item","—")),
                "Frente": "—",
                "Evento": r.get("tipo_evento", "—"),
                "Tramo": f"Est. {r.get('est_desde','?')} → {r.get('est_hasta','?')}",
                "Operador": r.get("operador", "—"),
                "Observación": r.get("nota", ""),
                "Fecha": r["created_at_dt"].strftime("%d-%m-%Y %H:%M"),
            })

    if rows_hist:
        df_hist_05 = pd.DataFrame(rows_hist).sort_values("Fecha", ascending=False)
        st.dataframe(df_hist_05, use_container_width=True, hide_index=True)
    else:
        st.info("Sin registros para CV005 aún.")

# ============================================================
# PESTAÑA ANÁLISIS DE CORTES
# ============================================================

def leer_historial_cortes() -> pd.DataFrame:
    try:
        resp = supabase.table("historial_cortes").select("*").execute()
        df = pd.DataFrame(resp.data)
        if not df.empty and "fecha_corte" in df.columns:
            df["fecha_corte"] = pd.to_datetime(df["fecha_corte"])
        return df
    except Exception as e:
        st.warning(f"⚠ Error leyendo historial_cortes: {e}")
        return pd.DataFrame()


CAUSAS_CORTE = [
    "Apretón",
    "Falla Fijación Rollo / Roce Correa",
    "Fricción con Correa",
    "Fricción con Viga",
    "Fricción con Corrugado",
    "Daño Rodamiento / Fricción",
    "Roce Polín",
    "Problema Caja de Fusión",
    "Tirón a fusión",
    "Otro",
]

with ftab_cortes:
    st.markdown("""
    <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:0 0 14px">
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
                    color:rgba(255,255,255,0.3);margin-bottom:4px">Estadísticas</div>
        <div style="font-size:17px;font-weight:500;color:#F0F2F5">
          Análisis de cortes — CV005 · CV006 · CV007
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    df_cortes = leer_historial_cortes()

    # Debug temporal — muestra si hay error de conexión o RLS
    if df_cortes.empty:
        try:
            resp_test = supabase.table("historial_cortes").select("id", count="exact").execute()
            st.info(f"Sin registros de cortes aún. Ejecuta el SQL inicial en Supabase. (Filas en tabla: {resp_test.count})")
        except Exception as e:
            st.error(f"Error accediendo a historial_cortes: {e} — Verifica RLS en Supabase (desactiva o agrega política pública)")
        st.stop()
    else:
        # ── Filtros ─────────────────────────────────────────────────────
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            filtro_correa = st.multiselect(
                "Correa", ["CV005", "CV006", "CV007"],
                default=["CV005", "CV006", "CV007"], key="fc_correa"
            )
        with fc2:
            filtro_tipo = st.multiselect(
                "Tipo de fibra", ["Troncal", "Sensitiva"],
                default=["Troncal", "Sensitiva"], key="fc_tipo"
            )
        with fc3:
            all_causas = sorted(df_cortes["causa_corte"].dropna().unique().tolist())
            filtro_causa = st.multiselect(
                "Causa", all_causas, default=all_causas, key="fc_causa"
            )

        df_f = df_cortes[
            df_cortes["correa_id"].isin(filtro_correa) &
            df_cortes["tipo_fibra"].isin(filtro_tipo) &
            df_cortes["causa_corte"].isin(filtro_causa)
        ].copy()

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # ── KPIs ────────────────────────────────────────────────────────
        kc1, kc2, kc3, kc4 = st.columns(4)
        causa_top = df_f["causa_corte"].value_counts().index[0] if not df_f.empty else "—"
        correa_top = df_f["correa_id"].value_counts().index[0] if not df_f.empty else "—"
        n_total = len(df_f)
        n_troncal = len(df_f[df_f["tipo_fibra"] == "Troncal"])
        n_sensitiva = len(df_f[df_f["tipo_fibra"] == "Sensitiva"])

        with kc1:
            st.markdown(kpi("Total de cortes", str(n_total),
                f"Troncal: {n_troncal} · Sensitiva: {n_sensitiva}", "#E24B4A"),
                unsafe_allow_html=True)
        with kc2:
            st.markdown(kpi("Causa más frecuente", causa_top,
                f"{df_f['causa_corte'].value_counts().iloc[0] if not df_f.empty else 0} ocurrencias",
                "#F59E0B"), unsafe_allow_html=True)
        with kc3:
            st.markdown(kpi("Correa con más cortes", correa_top,
                f"{df_f['correa_id'].value_counts().iloc[0] if not df_f.empty else 0} eventos",
                "#378ADD"), unsafe_allow_html=True)
        with kc4:
            if not df_f.empty and "fecha_corte" in df_f.columns:
                ultimo = df_f.sort_values("fecha_corte", ascending=False).iloc[0]
                ultimo_str = ultimo["fecha_corte"].strftime("%d-%m-%Y")
                ultimo_sub = f"{ultimo['correa_id']} · {ultimo['causa_corte']}"
            else:
                ultimo_str, ultimo_sub = "—", "—"
            st.markdown(kpi("Último corte registrado", ultimo_str, ultimo_sub, "#7F77DD"),
                unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # ── Gráfico interactivo con st.components ───────────────────────
        st.markdown("""
        <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
          Distribución de cortes
        </div>""", unsafe_allow_html=True)

        import json
        data_json = []
        for _, r in df_f.iterrows():
            data_json.append({
                "correa": r.get("correa_id", ""),
                "tipo":   r.get("tipo_fibra", ""),
                "causa":  r.get("causa_corte", ""),
                "est":    int(r["estacion"]) if pd.notna(r.get("estacion")) else None,
                "fecha":  r["fecha_corte"].strftime("%d-%m-%Y") if pd.notna(r.get("fecha_corte")) else "",
            })

        html_chart = f"""
<!DOCTYPE html><html><head>
<style>
* {{ box-sizing:border-box;margin:0;padding:0;font-family:'Inter',sans-serif; }}
body {{ background:#0D1117;color:#F0F2F5;padding:8px; }}
.charts {{ display:grid;grid-template-columns:1fr 1fr;gap:12px; }}
.card {{ background:#161B22;border:0.5px solid rgba(255,255,255,0.08);
         border-radius:10px;padding:14px 16px; }}
.card-title {{ font-size:10px;font-weight:600;color:rgba(255,255,255,0.35);
               text-transform:uppercase;letter-spacing:1px;margin-bottom:14px; }}
.bar-row {{ display:flex;align-items:center;gap:10px;margin-bottom:8px; }}
.bar-label {{ font-size:10px;color:rgba(255,255,255,0.55);width:185px;min-width:185px;
              text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
.bar-wrap {{ flex:1;background:rgba(255,255,255,0.07);border-radius:99px;height:9px;overflow:hidden; }}
.bar-fill {{ height:9px;border-radius:99px;transition:width .3s ease; }}
.bar-count {{ font-size:10px;font-weight:600;min-width:20px;text-align:left; }}
</style></head><body>
<div class="charts">
  <div class="card">
    <div class="card-title">Por causa de corte</div>
    <div id="causas"></div>
  </div>
  <div class="card">
    <div class="card-title">Por correa y tipo de fibra</div>
    <div id="grupos"></div>
  </div>
</div>
<script>
const data = {json.dumps(data_json)};
const COLORS  = {{CV005:"#E24B4A", CV006:"#378ADD", CV007:"#34D399"}};
const TCOLORS = {{Troncal:"#E24B4A", Sensitiva:"#7F77DD"}};

function renderBars(elId, entries) {{
  const el  = document.getElementById(elId);
  const max = entries[0]?.[1] || 1;
  el.innerHTML = entries.map(([label, count, color]) => `
    <div class="bar-row">
      <div class="bar-label" title="${{label}}">${{label}}</div>
      <div class="bar-wrap">
        <div class="bar-fill" style="width:${{(count/max*100).toFixed(1)}}%;background:${{color}};"></div>
      </div>
      <div class="bar-count" style="color:${{color}}">${{count}}</div>
    </div>`).join('');
}}

// ── Causas ──────────────────────────────────────────────
const causas = {{}};
data.forEach(d => {{
  if (!causas[d.causa]) causas[d.causa] = {{n:0, correas:{{}}}};
  causas[d.causa].n++;
  causas[d.causa].correas[d.correa] = (causas[d.causa].correas[d.correa]||0)+1;
}});
const causasArr = Object.entries(causas)
  .sort((a,b) => b[1].n - a[1].n)
  .map(([k,v]) => {{
    const sorted = Object.entries(v.correas).sort((a,b) => b[1]-a[1]);
    const color  = (sorted.length>1 && sorted[0][1]===sorted[1][1])
                   ? "#9CA3AF" : COLORS[sorted[0][0]];
    return [k, v.n, color];
  }});
renderBars('causas', causasArr);

// ── Por correa + tipo ────────────────────────────────────
const grupos = {{}};
data.forEach(d => {{
  const k = d.correa + ' · ' + d.tipo;
  if (!grupos[k]) grupos[k] = {{n:0, tipo:d.tipo}};
  grupos[k].n++;
}});
const gruposArr = Object.entries(grupos)
  .sort((a,b) => b[1].n - a[1].n)
  .map(([k,v]) => [k, v.n, TCOLORS[v.tipo]]);
renderBars('grupos', gruposArr);
</script></body></html>"""

        st.components.v1.html(html_chart, height=360, scrolling=False)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # ── Tabla detalle ────────────────────────────────────────────────
        st.markdown("""
        <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
          Registro detallado de cortes
        </div>""", unsafe_allow_html=True)

        df_tabla = df_f.copy()
        if "fecha_corte" in df_tabla.columns:
            df_tabla["Fecha"] = df_tabla["fecha_corte"].dt.strftime("%d-%m-%Y")
        cols_show = {
            "correa_id":   "Correa",
            "tipo_fibra":  "Tipo fibra",
            "estacion":    "Estación",
            "Fecha":       "Fecha corte",
            "causa_corte": "Causa",
            "nota":        "Ubicación / nota",
            "operador":    "Operador",
        }
        df_view = df_tabla[[c for c in cols_show if c in df_tabla.columns]].rename(columns=cols_show)
        df_view = df_view.sort_values("Fecha corte", ascending=False)
        st.dataframe(df_view, use_container_width=True, hide_index=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # ── Formulario registro nuevo corte ─────────────────────────────
        st.markdown("""
        <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
          Registrar nuevo corte
        </div>""", unsafe_allow_html=True)

        with st.form(key="form_nuevo_corte"):
            nc1, nc2, nc3 = st.columns(3)
            with nc1:
                nc_correa  = st.selectbox("Correa", ["CV005","CV006","CV007"], key="nc_correa")
                nc_tipo    = st.selectbox("Tipo de fibra", ["Troncal","Sensitiva"], key="nc_tipo")
            with nc2:
                nc_est     = st.number_input("Estación", min_value=1, max_value=3823,
                                              value=1, step=1, key="nc_est", format="%d")
                nc_fecha   = st.date_input("Fecha del corte", key="nc_fecha")
            with nc3:
                nc_causa   = st.selectbox("Causa del corte", CAUSAS_CORTE, key="nc_causa")
                nc_op      = st.text_input("Operador", key="nc_op", placeholder="Nombre")
            nc_nota = st.text_input("Ubicación / observación", key="nc_nota",
                                     placeholder="Ej: Estación de Carga 807")

            if st.form_submit_button("💾 Registrar corte"):
                if not nc_op.strip():
                    st.error("Ingresa el operador.")
                else:
                    try:
                        supabase.table("historial_cortes").insert({
                            "correa_id":   nc_correa,
                            "tipo_fibra":  nc_tipo,
                            "estacion":    int(nc_est),
                            "fecha_corte": str(nc_fecha),
                            "causa_corte": nc_causa,
                            "operador":    nc_op.strip(),
                            "nota":        nc_nota,
                        }).execute()
                        st.success(f"✅ Corte registrado — {nc_correa} · {nc_tipo} · Est. {nc_est}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
