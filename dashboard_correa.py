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
    fs = FACTORES[correa_id]["sensitiva"]
    metros_s = 0.0
    for frente in FRENTES.get(correa_id, ["unico"]):
        d, h = obtener_tramo_activo(df, 5, frente)
        if d is not None:
            metros_s += abs(h - d) * fs
    if not df.empty and "frente" not in df.columns:
        metros_s = sum(
            abs(int(r["estacion_hasta"]) - int(r["estacion_desde"])) * fs
            for _, r in df[df["nivel"].astype(int) == 5].iterrows()
        )
    total_s = SENSITIVA_TOTAL_MTS[correa_id]
    return {
        "metros_t": TRONCAL_TOTAL_MTS[correa_id],
        "metros_s": metros_s,
        "pct_s":    min(metros_s / total_s * 100, 100.0) if total_s > 0 else 0.0,
        "total_s":  total_s,
        "factor_t": FACTORES[correa_id]["troncal"],
        "factor_s": fs,
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
    border  = "rgba(99,153,34,0.2)" if completada else "rgba(255,255,255,0.08)"
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
        <span style="font-size:11px;color:rgba(255,255,255,0.5)">🔴 Troncal</span>
        <span style="font-size:11px;font-weight:500;color:#E24B4A">100.0%</span>
      </div>
      <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:6px;overflow:hidden">
        <div style="width:100%;background:#E24B4A;height:100%;border-radius:99px"></div>
      </div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-top:3px">
        {met['metros_t']:,.0f} m · {met['factor_t']:.2f} m/est
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

ftab05, ftab06, ftab07 = st.tabs(["➕ CV005", "➕ CV006", "➕ CV007"])

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

    st.markdown("---")
    st.markdown("""
    <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
      Calculadora SmartVision
    </div>""", unsafe_allow_html=True)

    calc_correa = st.selectbox("Correa", ["CV005","CV006","CV007"], key="calc_correa")
    calc_fibra  = st.selectbox("Tipo de fibra", [0, 5],
                    format_func=lambda x: "Troncal" if x == 0 else "Sensitiva", key="calc_fibra")
    calc_frente_opts = {
        "CV005": ["TP1 (origen Est. 3823)", "EM (origen Est. 1)"],
        "CV006": ["TP1 (origen Est. -3 / 3B Carga)", "TP2 (origen Est. 3526)"],
        "CV007": ["Único (origen Est. 3)"],
    }
    calc_frente_sel = st.selectbox("Frente / origen", calc_frente_opts[calc_correa], key="calc_frente")
    calc_metros = st.number_input("Metros SmartVision",
                    min_value=0.0, value=0.0, step=1.0, key="calc_metros", format="%.1f")

    factor_calc = FACTORES[calc_correa]["troncal"] if calc_fibra == 0 else FACTORES[calc_correa]["sensitiva"]
    origenes = {
        "CV005": {"TP1 (origen Est. 3823)": (3823, -1), "EM (origen Est. 1)": (1, 1)},
        "CV006": {"TP1 (origen Est. -3 / 3B Carga)": (-3, 1), "TP2 (origen Est. 3526)": (3526, -1)},
        "CV007": {"Único (origen Est. 3)": (3, 1)},
    }
    origen_est, direccion = origenes[calc_correa][calc_frente_sel]

    if factor_calc > 0 and calc_metros > 0:
        est_calc = round(origen_est + direccion * (calc_metros / factor_calc))
        rango = EST_RANGES[calc_correa]
        est_calc = max(rango["min"], min(rango["max"], est_calc))
        st.markdown(f"""
        <div style="background:rgba(55,138,221,0.1);border:0.5px solid rgba(55,138,221,0.3);
                    border-radius:8px;padding:12px 14px;margin-top:4px">
          <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-bottom:4px;
                      text-transform:uppercase;letter-spacing:.6px">Estación equivalente</div>
          <div style="font-size:26px;font-weight:500;color:#378ADD">Est. {est_calc:,}</div>
          <div style="font-size:10px;color:rgba(255,255,255,0.35);margin-top:4px">
            {calc_metros:,.1f} m ÷ {factor_calc:.3f} m/est = {calc_metros/factor_calc:.1f} est<br>
            Origen Est. {origen_est} {"↑" if direccion == 1 else "↓"} · {calc_correa}
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.06);
                    border-radius:8px;padding:10px 14px;margin-top:4px;
                    font-size:11px;color:rgba(255,255,255,0.3);text-align:center">
          Ingresa los metros para calcular
        </div>""", unsafe_allow_html=True)
