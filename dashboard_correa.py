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

def calcular_metraje(df, correa_id):
    ft = FACTORES[correa_id]["troncal"]
    fs = FACTORES[correa_id]["sensitiva"]

    metros_s = 0.0
    metros_t = 0.0
    troncal_completa = True  # asume 100% salvo que se detecte un corte vigente

    for frente in FRENTES.get(correa_id, ["unico"]):
        # Sensitiva: tramo activo más reciente (avance normal)
        d, h = obtener_tramo_activo(df, 5, frente)
        if d is not None:
            metros_s += abs(h - d) * fs

        # Troncal: revisar el registro más reciente de este frente
        sub_t = df[df["nivel"].astype(int) == 0].copy() if not df.empty else df
        if not sub_t.empty and "frente" in sub_t.columns:
            sub_t = sub_t[sub_t["frente"] == frente]
        if not sub_t.empty:
            if "created_at" in sub_t.columns:
                sub_t = sub_t.sort_values("created_at", ascending=False)
            ultimo = sub_t.iloc[0]
            tipo_ev = str(ultimo.get("tipo_evento", "")).strip().lower()
            d_t, h_t = int(ultimo["estacion_desde"]), int(ultimo["estacion_hasta"])
            tramo_t = abs(h_t - d_t) * ft

            if "corte" in tipo_ev:
                # Un corte vigente reduce el troncal de ese frente: se descuenta el tramo cortado
                troncal_completa = False
                metros_t += max(TRONCAL_TOTAL_MTS[correa_id] / len(FRENTES.get(correa_id, ["unico"])) - tramo_t, 0)
            else:
                # Avance / fusión / mantención: troncal de ese frente se considera operativo
                metros_t += TRONCAL_TOTAL_MTS[correa_id] / len(FRENTES.get(correa_id, ["unico"]))
        else:
            # Sin registros de troncal para este frente: se asume 100% (estado inicial de terreno)
            metros_t += TRONCAL_TOTAL_MTS[correa_id] / len(FRENTES.get(correa_id, ["unico"]))

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
    st.markdown(kpi("Troncal completada", "3 / 3",
        "CV005, CV006 y CV007 al 100%", "#639922"), unsafe_allow_html=True)
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

def render_card(col, nombre, met, completada, frentes_txt):
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
    frente_rows = "".join([
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
        f'<span style="font-size:10px;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:5px">'
        f'<span style="width:5px;height:5px;border-radius:50%;background:{f["color"]};display:inline-block"></span>'
        f'{f["label"]}</span>'
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

c1, c2, c3 = st.columns(3)

tp1_d, tp1_h = obtener_tramo_activo(df_05, 5, "tp1")
em_d,  em_h  = obtener_tramo_activo(df_05, 5, "em")
frentes_05 = []
if tp1_d is not None:
    frentes_05.append({"label":"Frente TP1","rango":f"Est. {tp1_d} → {tp1_h}","color":"#E24B4A"})
if em_d is not None:
    frentes_05.append({"label":"Frente EM","rango":f"Est. {em_d} → {em_h}","color":"#7F77DD"})
if not frentes_05:
    frentes_05 = [{"label":"Frente TP1","rango":"Est. 3823 → 2000","color":"#E24B4A"},
                  {"label":"Frente EM","rango":"Est. 1 → 2000","color":"#7F77DD"}]

t1d, t1h = obtener_tramo_activo(df_06, 5, "tp1")
t2d, t2h = obtener_tramo_activo(df_06, 5, "tp2")
frentes_06 = []
if t1d is not None:
    frentes_06.append({"label":"Frente TP1","rango":f"{MAPEO_NUM_A_LETRA.get(t1d,str(t1d))} → Est. {t1h}","color":"#E24B4A"})
if t2d is not None:
    frentes_06.append({"label":"Frente TP2","rango":f"Est. {t2d} → {t2h}","color":"#7F77DD"})
if not frentes_06:
    frentes_06 = [{"label":"Frente TP1","rango":"3B Carga → Est. 1845","color":"#E24B4A"},
                  {"label":"Frente TP2","rango":"Est. 3526 → 1846","color":"#7F77DD"}]

frentes_07 = [{"label":"Frente único","rango":"Est. 3 → 842","color":"#639922"}]

render_card(c1, "CV005", met_05, False, frentes_05)
render_card(c2, "CV006", met_06, False, frentes_06)
render_card(c3, "CV007", met_07, True,  frentes_07)

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

ftab05, ftab06, ftab07, ftab_pdf, ftab_esquema = st.tabs(
    ["➕ CV005", "➕ CV006", "➕ CV007", "📄 Reporte PDF", "🔧 Esquema de correas"]
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
        if c05_metros > 0:
            c05_est = max(EST_RANGES["CV005"]["min"], min(EST_RANGES["CV005"]["max"],
                          round(c05_orig[0] + c05_orig[1] * (c05_metros / c05_factor))))
            st.markdown(f"""<div style="background:rgba(55,138,221,0.1);border:0.5px solid rgba(55,138,221,0.3);
                        border-radius:8px;padding:10px 12px;margin-top:4px">
              <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-bottom:3px">Estación equivalente</div>
              <div style="font-size:22px;font-weight:500;color:#378ADD">Est. {c05_est:,}</div>
              <div style="font-size:10px;color:rgba(255,255,255,0.35);margin-top:3px">
                {c05_metros:,.1f} m ÷ {c05_factor:.3f} = {c05_metros/c05_factor:.1f} est
              </div></div>""", unsafe_allow_html=True)

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
    <div class="kpi-value">3 / 3</div>
    <div class="kpi-sub">CV005, CV006 y CV007 al 100%</div>
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
# ============================================================
def generar_svg_correa(correa_id, met, sens_frentes, label_izq, est_izq, label_der, est_der, doble=True):
    """
    Genera el SVG de la correa transportadora con dos carriles separados:
    troncal (arriba) y sensitiva (abajo), sin solaparse.

    sens_frentes: lista de dicts {pct, color, lado} para los segmentos de sensitiva
    label_izq/der, est_izq/der: etiquetas de los extremos (TP1/EM, 3B Carga/TP2, etc.)
    doble: si la correa tiene dos frentes (CV005/CV006) o uno solo (CV007)
    """
    w, h = 680, 300
    cx = w / 2
    x0, x1 = 90, 590
    largo = x1 - x0
    y_tambor = 140

    pct_t = min(met["pct_t"], 100.0)
    color_t = "#E24B4A" if met["pct_t"] >= 100 else "#f59e0b"

    parts = [f'''<svg width="100%" viewBox="0 0 {w} {h}" role="img">
<title>Esquema correa transportadora {correa_id}</title>
<desc>Vista lateral de la correa {correa_id} con tramo de carga y retorno, mostrando avance de fibra troncal y sensitiva en carriles separados</desc>
<defs>
<marker id="arrow_{correa_id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker>
</defs>
<text class="th" x="{cx}" y="24" text-anchor="middle">{correa_id}</text>''']

    # Tambores motrices
    parts.append(f'<circle cx="{x0}" cy="{y_tambor}" r="26" fill="none" stroke="var(--text-secondary)" stroke-width="3"/>')
    parts.append(f'<circle cx="{x0}" cy="{y_tambor}" r="8" fill="var(--text-secondary)" opacity="0.5"/>')
    parts.append(f'<circle cx="{x1}" cy="{y_tambor}" r="26" fill="none" stroke="var(--text-secondary)" stroke-width="3"/>')
    parts.append(f'<circle cx="{x1}" cy="{y_tambor}" r="8" fill="var(--text-secondary)" opacity="0.5"/>')

    # Tramo carga (arriba) y retorno (abajo)
    parts.append(f'<line x1="{x0}" y1="{y_tambor-26}" x2="{x1}" y2="{y_tambor-26}" stroke="var(--border-strong)" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<line x1="{x0}" y1="{y_tambor+26}" x2="{x1}" y2="{y_tambor+26}" stroke="var(--border)" stroke-width="3" stroke-linecap="round" opacity="0.5"/>')
    parts.append(f'<path d="M{x0},{y_tambor-26} A26,26 0 0,0 {x0},{y_tambor+26}" fill="none" stroke="var(--border-strong)" stroke-width="4"/>')
    parts.append(f'<path d="M{x1},{y_tambor-26} A26,26 0 0,1 {x1},{y_tambor+26}" fill="none" stroke="var(--border-strong)" stroke-width="4"/>')

    # Polines guía intermedios
    n_polines = 7
    for i in range(1, n_polines + 1):
        px = x0 + (largo / (n_polines + 1)) * i
        parts.append(f'<circle cx="{px:.1f}" cy="{y_tambor}" r="6" fill="var(--text-secondary)" opacity="0.4"/>')

    # ── Carril Troncal (arriba del tramo de carga) ──
    y_troncal = y_tambor - 26 - 18
    parts.append(f'<text class="ts" x="{x0-40}" y="{y_troncal+4}" text-anchor="end">Troncal</text>')
    parts.append(f'<line x1="{x0}" y1="{y_troncal+8}" x2="{x1}" y2="{y_troncal+8}" stroke="var(--border)" stroke-width="2" stroke-linecap="round" opacity="0.3"/>')
    ancho_troncal = largo * (pct_t / 100.0)
    parts.append(f'<rect x="{x0}" y="{y_troncal+4}" width="{ancho_troncal:.1f}" height="8" rx="4" fill="{color_t}" opacity="0.85"/>')

    # ── Carril Sensitiva (debajo del troncal, encima de la correa) ──
    y_sens = y_tambor - 26 - 4
    parts.append(f'<text class="ts" x="{x0-40}" y="{y_sens+4}" text-anchor="end">Sensitiva</text>')
    parts.append(f'<line x1="{x0}" y1="{y_sens+8}" x2="{x1}" y2="{y_sens+8}" stroke="var(--border)" stroke-width="2" stroke-linecap="round" opacity="0.3"/>')

    leyenda_items = []
    for f in sens_frentes:
        pct = min(f["pct"], 100.0)
        ancho = (largo / (2 if doble else 1)) * (pct / 100.0)
        if f["lado"] == "izq":
            sx = x0
        else:
            sx = x1 - ancho
        parts.append(f'<rect x="{sx:.1f}" y="{y_sens+4}" width="{ancho:.1f}" height="8" rx="4" fill="{f["color"]}" opacity="0.9"/>')
        leyenda_items.append(f)

    # Centro
    parts.append(f'<circle cx="{cx}" cy="{y_tambor}" r="4" fill="#0C447C"/>')
    parts.append(f'<line x1="{cx}" y1="{y_troncal-20}" x2="{cx}" y2="{y_troncal+2}" stroke="var(--border-strong)" stroke-width="0.5" stroke-dasharray="2 2"/>')
    parts.append(f'<text class="ts" x="{cx}" y="{y_troncal-26}" text-anchor="middle">Centro</text>')

    # Labels extremos
    y_ext = y_tambor + 70
    parts.append(f'<text class="th" x="{x0}" y="{y_ext}" text-anchor="middle">{label_izq}</text>')
    parts.append(f'<text class="ts" x="{x0}" y="{y_ext+16}" text-anchor="middle">{est_izq}</text>')
    if doble:
        parts.append(f'<text class="th" x="{x1}" y="{y_ext}" text-anchor="middle">{label_der}</text>')
        parts.append(f'<text class="ts" x="{x1}" y="{y_ext+16}" text-anchor="middle">{est_der}</text>')

    # Detalle texto
    y_det = y_ext + 42
    sub_t = "100% completa" if met["troncal_completa"] else "⚠ con corte activo"
    parts.append(f'<text class="ts" x="{cx}" y="{y_det}" text-anchor="middle">Troncal: {met["metros_t"]:,.0f} m · {sub_t} · {met["factor_t"]:.2f} m/est</text>')

    y_det2 = y_det + 16
    detalle_sens = "  ·  ".join([f["detalle"] for f in sens_frentes])
    parts.append(f'<text class="ts" x="{cx}" y="{y_det2}" text-anchor="middle">{detalle_sens}</text>')

    # Leyenda
    y_leg = y_det2 + 30
    x_leg = 170
    parts.append(f'<g class="c-red"><rect x="{x_leg}" y="{y_leg-10}" width="12" height="12" rx="3" stroke-width="0.5"/></g>')
    parts.append(f'<text class="ts" x="{x_leg+20}" y="{y_leg}">Troncal</text>')
    x_leg += 100
    for f in leyenda_items:
        parts.append(f'<g><rect x="{x_leg}" y="{y_leg-10}" width="12" height="12" rx="3" fill="{f["color"]}" opacity="0.9"/></g>')
        parts.append(f'<text class="ts" x="{x_leg+20}" y="{y_leg}">{f["nombre"]}</text>')
        x_leg += 130

    parts.append('</svg>')
    return "".join(parts)


with ftab_esquema:
    st.markdown("""
    <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.07);
                border-radius:10px;padding:14px 16px;margin-bottom:16px">
      <div style="font-size:13px;font-weight:500;color:#F0F2F5;margin-bottom:4px">Distribución física de fibra</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.4)">
        Vista lateral de cada correa transportadora con sus dos tambores motrices, mostrando el avance
        real de fibra troncal y sensitiva en carriles separados desde cada frente de trabajo.
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    .esquema-svg-wrap text.th { fill: var(--text-primary, #F0F2F5); font-size: 14px; font-weight: 500; font-family: inherit; }
    .esquema-svg-wrap text.ts { fill: rgba(255,255,255,0.45); font-size: 11px; font-family: inherit; }
    .esquema-card { background:rgba(255,255,255,0.03); border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:12px; padding:12px 8px; margin-bottom:18px; }
    </style>
    """, unsafe_allow_html=True)

    # ── CV005 ──
    tp1_d, tp1_h = obtener_tramo_activo(df_05, 5, "tp1")
    em_d,  em_h  = obtener_tramo_activo(df_05, 5, "em")
    pct_tp1_05 = min(abs((tp1_d if tp1_d is not None else 3823) - (tp1_h or 2000)) / (3823-2000) * 100, 100) if tp1_d else 0
    pct_em_05  = min(abs((em_d if em_d is not None else 1) - (em_h or 2000)) / (2000-1) * 100, 100) if em_d else 0

    sens_05 = [
        {"lado":"izq","pct":pct_tp1_05,"color":"#7F77DD","nombre":"Sensitiva TP1",
         "detalle": f"Sensitiva TP1: Est. {tp1_d if tp1_d is not None else 3823} → {tp1_h if tp1_h is not None else 2000}"},
        {"lado":"der","pct":pct_em_05,"color":"#1D9E75","nombre":"Sensitiva EM",
         "detalle": f"Sensitiva EM: Est. {em_d if em_d is not None else 1} → {em_h if em_h is not None else 2000}"},
    ]
    svg_05 = generar_svg_correa("CV005", met_05, sens_05, "TP1", "Est. 3823", "EM", "Est. 1", doble=True)
    st.markdown(f'<div class="esquema-card esquema-svg-wrap">{svg_05}</div>', unsafe_allow_html=True)

    # ── CV006 ──
    t1d, t1h = obtener_tramo_activo(df_06, 5, "tp1")
    t2d, t2h = obtener_tramo_activo(df_06, 5, "tp2")
    pct_tp1_06 = min(abs((t1d if t1d is not None else -3) - (t1h or 1845)) / (1845-(-3)) * 100, 100) if t1d is not None else 0
    pct_tp2_06 = min(abs((t2d if t2d is not None else 3526) - (t2h or 1846)) / (3526-1846) * 100, 100) if t2d else 0
    t1d_label = MAPEO_NUM_A_LETRA.get(t1d, str(t1d)) if t1d is not None else "3B Carga"

    sens_06 = [
        {"lado":"izq","pct":pct_tp1_06,"color":"#7F77DD","nombre":"Sensitiva TP1",
         "detalle": f"Sensitiva TP1: {t1d_label} → {t1h if t1h is not None else 1845}"},
        {"lado":"der","pct":pct_tp2_06,"color":"#1D9E75","nombre":"Sensitiva TP2",
         "detalle": f"Sensitiva TP2: Est. {t2d if t2d is not None else 3526} → {t2h if t2h is not None else 1846}"},
    ]
    svg_06 = generar_svg_correa("CV006", met_06, sens_06, "TP1", "3B Carga", "TP2", "Est. 3526", doble=True)
    st.markdown(f'<div class="esquema-card esquema-svg-wrap">{svg_06}</div>', unsafe_allow_html=True)

    # ── CV007 ──
    u_d, u_h = obtener_tramo_activo(df_07, 5, "unico")
    pct_unico_07 = min(abs((u_d if u_d is not None else 3) - (u_h or 842)) / (842-3) * 100, 100) if u_d else 100

    sens_07 = [
        {"lado":"izq","pct":pct_unico_07,"color":"#1D9E75","nombre":"Sensitiva",
         "detalle": f"Frente único: Est. {u_d if u_d is not None else 3} → {u_h if u_h is not None else 842}"},
    ]
    svg_07 = generar_svg_correa("CV007", met_07, sens_07, "TP2", "Est. 3", "Shuttler", "Est. 842", doble=False)
    st.markdown(f'<div class="esquema-card esquema-svg-wrap">{svg_07}</div>', unsafe_allow_html=True)
