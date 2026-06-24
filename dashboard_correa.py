"""
Sistema de Monitoreo de Polines mediante Fibra Óptica
Dashboard v2 — CV005 / CV006 / CV007
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
import base64

# ============================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ============================================================
st.set_page_config(
    layout="wide",
    page_title="Monitoreo Fibra Óptica — CV",
    page_icon="🔴",
)

# ============================================================
# 2. CONSTANTES DE INGENIERÍA
# ============================================================
FACTORES = {
    "CV005": {"troncal": 1.547, "sensitiva": 10.83},
    "CV006": {"troncal": 1.665, "sensitiva": 13.66},
    "CV007": {"troncal": 1.595, "sensitiva": 17.36},
}

EST_RANGES = {
    "CV005": {"min": 1,  "max": 3823, "total": 3822},
    "CV006": {"min": -3, "max": 3526, "total": 3529},
    "CV007": {"min": 3,  "max": 842,  "total": 839},
}

SENSITIVA_TOTAL_MTS = {
    "CV005": 41402.0,
    "CV006": 48214.0,
    "CV007": 14568.0,
}

TRONCAL_TOTAL_MTS = {
    "CV005": 5916.0,
    "CV006": 5876.0,
    "CV007": 1339.0,
}

MAPEO_NUM_A_LETRA = {-3: "3B Carga", -2: "2B Carga", -1: "1B Carga"}

NIVELES = {
    0: {"nombre": "Fibra Óptica Troncal",               "color": "#E24B4A", "glow": "rgba(226,75,74,0.18)"},
    5: {"nombre": "Fibra Óptica Sensitiva Monitoreada", "color": "#7F77DD", "glow": "rgba(127,119,221,0.18)"},
}

FRENTES = {
    "CV005": ["tp1", "em"],
    "CV006": ["tp1", "tp2"],
    "CV007": ["unico"],
}

TIPOS_EVENTO = ["Avance de fibra", "Corte", "Fusión / empalme", "Mantención", "Otro"]

# ============================================================
# 3. CONEXIÓN SUPABASE
# ============================================================
SUPABASE_URL = "https://aumkuyciwmeevnwtsvpy.supabase.co"
SUPABASE_KEY = "sb_publishable_5Iq0mHkNsetilyAFFQo1tw_-dth1liU"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_supabase()
except Exception as e:
    st.error(f"Error de conexión con Supabase: {e}")
    st.stop()

# ============================================================
# 4. BASE DE DATOS
# ============================================================

def leer_datos(correa_id: str) -> pd.DataFrame:
    try:
        resp = (
            supabase.table("eventos_correa")
            .select("*")
            .eq("correa_id", correa_id)
            .in_("nivel", [0, 5])
            .execute()
        )
        df = pd.DataFrame(resp.data)
        if not df.empty and correa_id == "CV006":
            df["est_desde_label"] = df["estacion_desde"].apply(
                lambda x: MAPEO_NUM_A_LETRA.get(int(x), str(x))
            )
            df["est_hasta_label"] = df["estacion_hasta"].apply(
                lambda x: MAPEO_NUM_A_LETRA.get(int(x), str(x))
            )
        return df
    except Exception:
        return pd.DataFrame()


def guardar_registro(operador, desde, hasta, nivel, nota, tipo_evento, correa_id, frente) -> bool:
    try:
        nuevo = {
            "operador":        operador,
            "estacion_desde":  int(desde),
            "estacion_hasta":  int(hasta),
            "nivel":           int(nivel),
            "nota":            nota,
            "tipo_evento":     tipo_evento,
            "correa_id":       correa_id,
            "frente":          frente,
        }
        supabase.table("eventos_correa").insert(nuevo).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar en Supabase: {e}")
        return False


def leer_historial_reciente(limit: int = 50) -> pd.DataFrame:
    dfs = []
    for cid in ["CV005", "CV006", "CV007"]:
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
# 5. CÁLCULO
# ============================================================

def obtener_tramo_activo(df: pd.DataFrame, nivel: int, frente: str):
    if df.empty:
        return None, None
    sub = df[df["nivel"].astype(int) == nivel]
    if "frente" in sub.columns:
        sub = sub[sub["frente"] == frente]
    if sub.empty:
        return None, None
    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at", ascending=False)
    row = sub.iloc[0]
    return int(row["estacion_desde"]), int(row["estacion_hasta"])


def calcular_metraje(df: pd.DataFrame, correa_id: str) -> dict:
    ft = FACTORES[correa_id]["troncal"]
    fs = FACTORES[correa_id]["sensitiva"]
    metros_s = 0.0

    for frente in FRENTES.get(correa_id, ["unico"]):
        d, h = obtener_tramo_activo(df, 5, frente)
        if d is not None and h is not None:
            metros_s += abs(h - d) * fs

    if not df.empty and "frente" not in df.columns:
        metros_s = 0.0
        for _, row in df[df["nivel"].astype(int) == 5].iterrows():
            metros_s += abs(int(row["estacion_hasta"]) - int(row["estacion_desde"])) * fs

    total_s = SENSITIVA_TOTAL_MTS[correa_id]
    metros_t = TRONCAL_TOTAL_MTS[correa_id]
    pct_s = min((metros_s / total_s) * 100, 100.0) if total_s > 0 else 0.0

    return {
        "metros_t": metros_t,
        "metros_s": metros_s,
        "pct_t":    100.0,
        "pct_s":    pct_s,
        "factor_t": ft,
        "factor_s": fs,
        "total_s":  total_s,
    }


def estacion_a_metros(estacion: int, correa_id: str, nivel: int) -> float:
    factor = FACTORES[correa_id]["troncal"] if nivel == 0 else FACTORES[correa_id]["sensitiva"]
    origen = EST_RANGES[correa_id]["min"]
    return abs(int(estacion) - origen) * factor

# ============================================================
# 6. ESTILOS
# ============================================================

def apply_styles():
    st.markdown("""
    <style>
    /* Reset padding del header de Streamlit */
    #root > div:first-child { padding-top: 0 !important; }
    .stAppHeader { display: none !important; }
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.2rem !important;
        padding-left: 1.8rem !important;
        padding-right: 1.8rem !important;
    }

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    [data-testid="stAppViewContainer"] {
        background-color: #0D1117;
    }
    [data-testid="stSidebar"] {
        background: #0A0E15 !important;
        border-right: 0.5px solid rgba(255,255,255,0.07) !important;
    }
    [data-testid="stSidebar"] > div { padding-top: 1rem; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.04);
        border-radius: 8px;
        padding: 3px;
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: rgba(255,255,255,0.45);
        font-size: 12px;
        padding: 5px 16px;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(55,138,221,0.15) !important;
        color: #378ADD !important;
        font-weight: 500;
    }
    /* Botones sidebar */
    .stButton > button {
        background: rgba(55,138,221,0.1);
        border: 0.5px solid rgba(55,138,221,0.3);
        color: #378ADD;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 500;
        width: 100%;
        padding: 7px 0;
    }
    .stButton > button:hover {
        background: rgba(55,138,221,0.2);
        border-color: rgba(55,138,221,0.55);
    }
    .stAlert { border-radius: 8px; font-size: 12px; }
    hr { border-color: rgba(255,255,255,0.07) !important; }
    [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    div[data-testid="stExpander"] {
        background: rgba(255,255,255,0.03);
        border: 0.5px solid rgba(255,255,255,0.08) !important;
        border-radius: 8px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 7. COMPONENTES HTML
# ============================================================

def html_header():
    st.markdown("""
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                padding:6px 0 18px">
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
                    color:rgba(255,255,255,0.3);margin-bottom:5px">
          Centro de telemetría térmica avanzada
        </div>
        <div style="font-size:19px;font-weight:500;color:#F0F2F5">
          Sistema de monitoreo de polines — fibra óptica
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:7px;padding-top:8px">
        <span style="width:7px;height:7px;border-radius:50%;background:#4CAF50;
                     display:inline-block"></span>
        <span style="font-size:11px;color:rgba(255,255,255,0.4)">Sistema en línea</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def html_kpi(label, value, sub, color):
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.08);
                border-radius:10px;padding:13px 15px;height:100%">
      <div style="font-size:10px;color:rgba(255,255,255,0.4);display:flex;align-items:center;
                  gap:6px;margin-bottom:7px;text-transform:uppercase;letter-spacing:.6px">
        <span style="width:7px;height:7px;border-radius:2px;background:{color};
                     display:inline-block"></span>{label}
      </div>
      <div style="font-size:21px;font-weight:500;color:#F0F2F5;margin-bottom:4px">{value}</div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3)">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def html_progress_bar(label, pct, color, metros, total, factor):
    pct_w = min(pct, 100.0)
    st.markdown(f"""
    <div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px">
        <span style="font-size:11px;color:rgba(255,255,255,0.5)">{label}</span>
        <span style="font-size:11px;font-weight:500;color:{color}">{pct:.1f}%</span>
      </div>
      <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:6px;overflow:hidden">
        <div style="width:{pct_w}%;background:{color};height:100%;border-radius:99px;
                    transition:width .4s ease"></div>
      </div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-top:3px">
        {metros:,.0f} m / ~{total:,.0f} m &nbsp;·&nbsp; {factor:.2f} m/est
      </div>
    </div>
    """, unsafe_allow_html=True)


def html_correa_card_header(nombre, completada: bool, metros_t, metros_s, total_s):
    badge = (
        '<span style="font-size:10px;padding:2px 9px;border-radius:99px;'
        'background:rgba(99,153,34,0.15);color:#8dc63f;'
        'border:0.5px solid rgba(99,153,34,0.3)">100% completada</span>'
        if completada else
        '<span style="font-size:10px;padding:2px 9px;border-radius:99px;'
        'background:rgba(55,138,221,0.1);color:#378ADD;'
        'border:0.5px solid rgba(55,138,221,0.25)">En progreso</span>'
    )
    border_color = "rgba(99,153,34,0.2)" if completada else "rgba(255,255,255,0.08)"
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.03);border:0.5px solid {border_color};
                border-radius:12px;padding:15px 16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-size:15px;font-weight:500;color:#F0F2F5">{nombre}</span>
        {badge}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
        <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:9px 11px">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;
                      color:rgba(255,255,255,0.35);margin-bottom:3px">Troncal</div>
          <div style="font-size:15px;font-weight:500;color:#F0F2F5">{metros_t:,.0f} m</div>
          <div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:2px">100% completa</div>
        </div>
        <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:9px 11px">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;
                      color:rgba(255,255,255,0.35);margin-bottom:3px">Sensitiva</div>
          <div style="font-size:15px;font-weight:500;color:#F0F2F5">{metros_s:,.0f} m</div>
          <div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:2px">de {total_s:,.0f} m</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def html_frentes(frentes_info: list):
    """frentes_info: list de dicts con keys: label, desde, hasta"""
    rows = ""
    for f in frentes_info:
        rows += f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span style="font-size:10px;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:5px">
            <span style="width:5px;height:5px;border-radius:50%;background:{f['color']};
                         display:inline-block"></span>{f['label']}
          </span>
          <span style="font-size:10px;color:rgba(255,255,255,0.5)">{f['desde']} → {f['hasta']}</span>
        </div>
        """
    st.markdown(f"""
    <div style="border-top:0.5px solid rgba(255,255,255,0.06);padding-top:9px;margin-top:2px">
      {rows}
    </div>
    """, unsafe_allow_html=True)


def html_section_title(title: str):
    st.markdown(f"""
    <div style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.4);
                text-transform:uppercase;letter-spacing:1px;margin:4px 0 8px">
      {title}
    </div>
    """, unsafe_allow_html=True)


def html_hist_table(df_hist: pd.DataFrame):
    """Renderiza el historial como tabla HTML estilizada."""
    if df_hist.empty:
        st.info("Sin registros en la base de datos aún.")
        return

    tag_colors = {
        "Avance de fibra": ("rgba(55,138,221,0.12)", "#5DA8E8", "rgba(55,138,221,0.2)"),
        "Corte":           ("rgba(226,75,74,0.12)",  "#E86E6D", "rgba(226,75,74,0.2)"),
        "Fusión / empalme":("rgba(99,153,34,0.12)",  "#8dc63f", "rgba(99,153,34,0.2)"),
        "Mantención":      ("rgba(186,117,23,0.12)", "#D4941F", "rgba(186,117,23,0.2)"),
        "Otro":            ("rgba(255,255,255,0.06)", "rgba(255,255,255,0.5)", "rgba(255,255,255,0.12)"),
    }
    nivel_colors = {
        0: ("rgba(226,75,74,0.12)",  "#E86E6D", "rgba(226,75,74,0.2)"),
        5: ("rgba(127,119,221,0.15)","#9F9AE8", "rgba(127,119,221,0.25)"),
    }

    rows_html = ""
    for _, row in df_hist.iterrows():
        te = row.get("tipo_evento", "Otro")
        bg_t, col_t, bord_t = tag_colors.get(te, tag_colors["Otro"])

        niv = int(row.get("nivel", 5))
        bg_n, col_n, bord_n = nivel_colors.get(niv, nivel_colors[5])
        niv_label = "Troncal" if niv == 0 else "Sensitiva"

        correa  = row.get("correa_id", "—")
        frente  = row.get("frente", "—")
        op      = row.get("operador", "—")
        d       = row.get("estacion_desde", "—")
        h       = row.get("estacion_hasta", "—")
        nota    = row.get("nota", "")
        fecha   = row.get("Fecha registro", "—")

        tramo_txt = f"Est. {d} → {h}"
        if correa == "CV006":
            d_l = MAPEO_NUM_A_LETRA.get(int(d) if str(d).lstrip("-").isdigit() else 0, str(d))
            h_l = MAPEO_NUM_A_LETRA.get(int(h) if str(h).lstrip("-").isdigit() else 0, str(h))
            tramo_txt = f"{d_l} → {h_l}"

        obs = f" · {nota}" if nota else ""

        rows_html += f"""
        <div style="display:grid;grid-template-columns:60px 110px 85px 1fr 130px 140px;
                    gap:0;padding:7px 14px;border-bottom:0.5px solid rgba(255,255,255,0.04);
                    align-items:center">
          <span style="font-size:11px;color:rgba(255,255,255,0.7)">{correa}</span>
          <span>
            <span style="font-size:9px;padding:2px 7px;border-radius:99px;
                         background:{bg_t};color:{col_t};border:0.5px solid {bord_t}">{te}</span>
          </span>
          <span>
            <span style="font-size:9px;padding:2px 7px;border-radius:99px;
                         background:{bg_n};color:{col_n};border:0.5px solid {bord_n}">{niv_label}</span>
          </span>
          <span style="font-size:10px;color:rgba(255,255,255,0.45)">{tramo_txt} · {frente}{obs}</span>
          <span style="font-size:10px;color:rgba(255,255,255,0.55)">{op}</span>
          <span style="font-size:10px;color:rgba(255,255,255,0.4)">{fecha}</span>
        </div>
        """

    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.02);border:0.5px solid rgba(255,255,255,0.07);
                border-radius:10px;overflow:hidden;margin-top:4px">
      <div style="padding:10px 14px;border-bottom:0.5px solid rgba(255,255,255,0.06);
                  display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:12px;font-weight:500;color:rgba(255,255,255,0.6)">
          Historial de registros de campo
        </span>
        <span style="font-size:10px;color:rgba(255,255,255,0.3);background:rgba(255,255,255,0.06);
                     padding:2px 9px;border-radius:99px">Últimos {len(df_hist)} eventos</span>
      </div>
      <div style="display:grid;grid-template-columns:60px 110px 85px 1fr 130px 140px;
                  gap:0;padding:6px 14px;background:rgba(255,255,255,0.03)">
        <span style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.6px">Correa</span>
        <span style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.6px">Tipo evento</span>
        <span style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.6px">Fibra</span>
        <span style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.6px">Tramo / observación</span>
        <span style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.6px">Operador</span>
        <span style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.6px">Fecha</span>
      </div>
      {rows_html}
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 8. GRÁFICOS TÉCNICOS (dentro de expander)
# ============================================================

def get_base64_img(path: str):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


def _add_segmento(fig, xd, xh, niv, row_data, correa_id, label_d=None, label_h=None):
    md  = estacion_a_metros(xd, correa_id, niv)
    mh  = estacion_a_metros(xh, correa_id, niv)
    ld  = label_d or str(xd)
    lh  = label_h or str(xh)
    op   = row_data.get("operador", "—") if isinstance(row_data, dict) else "—"
    nota = row_data.get("nota", "—")    if isinstance(row_data, dict) else "—"

    fig.add_trace(go.Scatter(
        x=[xd, xh], y=[niv, niv], mode="lines",
        line=dict(color=NIVELES[niv]["glow"], width=14),
        hoverinfo="skip", showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=[xd, xh], y=[niv, niv], mode="lines+markers",
        line=dict(color=NIVELES[niv]["color"], width=3),
        marker=dict(size=7, color=NIVELES[niv]["color"]),
        customdata=[[ld, md, op, nota], [lh, mh, op, nota]],
        hovertemplate=(
            f"<b>{NIVELES[niv]['nombre']}</b><br>"
            "📍 Estación: %{customdata[0]}<br>"
            "📏 Posición: %{customdata[1]:.1f} m<br>"
            "👷 Operador: %{customdata[2]}<br>"
            "📝 %{customdata[3]}<extra></extra>"
        ),
        showlegend=False
    ))


def _layout_base(fig):
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=10, b=35),
        height=260,
        yaxis=dict(
            range=[-2.5, 7.5],
            tickvals=list(NIVELES.keys()),
            ticktext=[n["nombre"] for n in NIVELES.values()],
            color="rgba(255,255,255,0.45)",
            gridcolor="rgba(255,255,255,0.04)",
        ),
    )


def build_figure_cv005(df, img_b64):
    def tx(est):
        e = int(est)
        return -(e - 2000) if e >= 2000 else (2000 - e)

    fig = go.Figure()
    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y", x=-1823, y=-0.5,
            sizex=3823, sizey=2.5, sizing="stretch", opacity=0.8, layer="below"
        ))
    if not df.empty:
        for niv in [0, 5]:
            for frente in ["tp1", "em"]:
                d, h = obtener_tramo_activo(df, niv, frente)
                if d is None:
                    continue
                sub = df[df["nivel"].astype(int) == niv]
                if "frente" in sub.columns:
                    sub = sub[sub["frente"] == frente]
                if not sub.empty and "created_at" in sub.columns:
                    sub = sub.sort_values("created_at", ascending=False)
                row_data = sub.iloc[0].to_dict() if not sub.empty else {}
                _add_segmento(fig, tx(d), tx(h), niv, row_data, "CV005", str(d), str(h))

    _layout_base(fig)
    fig.update_layout(xaxis=dict(
        tickvals=[-1823, -1000, 0, 1000, 1999],
        ticktext=["TP1 (3823)", "3000", "Centro (2000)", "1000", "EM (1)"],
        gridcolor="rgba(255,255,255,0.04)", color="rgba(255,255,255,0.45)",
    ))
    return fig


def build_figure_cv006(df, img_b64):
    fig = go.Figure()
    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y", x=-3, y=-0.5,
            sizex=3530, sizey=2.5, sizing="stretch", opacity=0.8, layer="below"
        ))
    if not df.empty:
        for niv in [0, 5]:
            for frente in ["tp1", "tp2"]:
                d, h = obtener_tramo_activo(df, niv, frente)
                if d is None:
                    continue
                sub = df[df["nivel"].astype(int) == niv]
                if "frente" in sub.columns:
                    sub = sub[sub["frente"] == frente]
                if not sub.empty and "created_at" in sub.columns:
                    sub = sub.sort_values("created_at", ascending=False)
                row_data = sub.iloc[0].to_dict() if not sub.empty else {}
                pts = sorted([d, h])
                ld = MAPEO_NUM_A_LETRA.get(pts[0], str(pts[0]))
                lh = MAPEO_NUM_A_LETRA.get(pts[1], str(pts[1]))
                _add_segmento(fig, pts[0], pts[1], niv, row_data, "CV006", ld, lh)

    _layout_base(fig)
    fig.update_layout(xaxis=dict(
        range=[-10, 3540],
        tickvals=[-3, 1845, 1846, 3526],
        ticktext=["3B Carga (TP1)", "Centro (1845)", "Centro (1846)", "TP2 (3526)"],
        gridcolor="rgba(255,255,255,0.04)", color="rgba(255,255,255,0.45)",
    ))
    return fig


def build_figure_cv007(df, img_b64):
    fig = go.Figure()
    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y", x=3, y=-0.5,
            sizex=839 * 2, sizey=2.5, sizing="stretch", opacity=0.8, layer="below"
        ))
    if not df.empty:
        for niv in [0, 5]:
            d, h = obtener_tramo_activo(df, niv, "unico")
            if d is None:
                continue
            sub = df[df["nivel"].astype(int) == niv]
            if not sub.empty and "created_at" in sub.columns:
                sub = sub.sort_values("created_at", ascending=False)
            row_data = sub.iloc[0].to_dict() if not sub.empty else {}
            pts = sorted([d, h])
            _add_segmento(fig, pts[0], pts[1], niv, row_data, "CV007")

    _layout_base(fig)
    fig.update_layout(xaxis=dict(
        range=[0, 855],
        tickvals=[3, 200, 400, 600, 842],
        ticktext=["TP2 (Est. 3)", "200", "400", "600", "Shuttler (Est. 842)"],
        gridcolor="rgba(255,255,255,0.04)", color="rgba(255,255,255,0.45)",
    ))
    return fig

# ============================================================
# 9. APP PRINCIPAL
# ============================================================

apply_styles()

img_tecnica_b64 = get_base64_img("correa_tecnica.png")

# ── Leer datos ──────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    df_05 = leer_datos("CV005")
    df_06 = leer_datos("CV006")
    df_07 = leer_datos("CV007")

met_05 = calcular_metraje(df_05, "CV005")
met_06 = calcular_metraje(df_06, "CV006")
met_07 = calcular_metraje(df_07, "CV007")

# ── Header ──────────────────────────────────────────────────
html_header()

# ── KPIs ────────────────────────────────────────────────────
total_t = met_05["metros_t"] + met_06["metros_t"] + met_07["metros_t"]
total_s = met_05["metros_s"] + met_06["metros_s"] + met_07["metros_s"]
total_s_pos = sum(SENSITIVA_TOTAL_MTS.values())
pct_global = (total_s / total_s_pos * 100) if total_s_pos > 0 else 0

k1, k2, k3, k4 = st.columns(4)
with k1:
    html_kpi("Troncal desplegada", f"{total_t:,.0f} m",
             f"CV005: {met_05['metros_t']:,.0f} · CV006: {met_06['metros_t']:,.0f} · CV007: {met_07['metros_t']:,.0f}",
             "#E24B4A")
with k2:
    html_kpi("Sensitiva desplegada", f"{total_s:,.0f} m",
             f"CV005: {met_05['metros_s']:,.0f} · CV006: {met_06['metros_s']:,.0f} · CV007: {met_07['metros_s']:,.0f}",
             "#7F77DD")
with k3:
    html_kpi("Troncal completada", "3 / 3",
             "CV005, CV006 y CV007 al 100%", "#639922")
with k4:
    html_kpi("Cobertura sensitiva global", f"{pct_global:.1f}%",
             f"{total_s:,.0f} m de ~{total_s_pos:,.0f} m", "#BA7517")

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ── Cards por correa ─────────────────────────────────────────
html_section_title("Estado por correa")
c1, c2, c3 = st.columns(3)

# ── CV005 ────────────────────────────────────────────────────
with c1:
    html_correa_card_header("CV005", False,
                            met_05["metros_t"], met_05["metros_s"], met_05["total_s"])
    html_progress_bar("🔴 Troncal",   met_05["pct_t"], "#E24B4A",
                      met_05["metros_t"], met_05["metros_t"], met_05["factor_t"])
    html_progress_bar("🟣 Sensitiva", met_05["pct_s"], "#7F77DD",
                      met_05["metros_s"], met_05["total_s"], met_05["factor_s"])

    tp1_d, tp1_h = obtener_tramo_activo(df_05, 5, "tp1")
    em_d,  em_h  = obtener_tramo_activo(df_05, 5, "em")
    frentes_05 = []
    if tp1_d is not None:
        frentes_05.append({"label": "Frente TP1", "desde": f"Est. {tp1_d}", "hasta": f"Est. {tp1_h}", "color": "#E24B4A"})
    if em_d is not None:
        frentes_05.append({"label": "Frente EM",  "desde": f"Est. {em_d}",  "hasta": f"Est. {em_h}",  "color": "#7F77DD"})
    if frentes_05:
        html_frentes(frentes_05)

    with st.expander("Ver detalle técnico"):
        st.plotly_chart(build_figure_cv005(df_05, img_tecnica_b64),
                        use_container_width=True, key="gr05")

# ── CV006 ────────────────────────────────────────────────────
with c2:
    html_correa_card_header("CV006", False,
                            met_06["metros_t"], met_06["metros_s"], met_06["total_s"])
    html_progress_bar("🔴 Troncal",   met_06["pct_t"], "#E24B4A",
                      met_06["metros_t"], met_06["metros_t"], met_06["factor_t"])
    html_progress_bar("🟣 Sensitiva", met_06["pct_s"], "#7F77DD",
                      met_06["metros_s"], met_06["total_s"], met_06["factor_s"])

    t1d, t1h = obtener_tramo_activo(df_06, 5, "tp1")
    t2d, t2h = obtener_tramo_activo(df_06, 5, "tp2")
    frentes_06 = []
    if t1d is not None:
        ld = MAPEO_NUM_A_LETRA.get(t1d, str(t1d))
        frentes_06.append({"label": "Frente TP1", "desde": ld, "hasta": f"Est. {t1h}", "color": "#E24B4A"})
    if t2d is not None:
        frentes_06.append({"label": "Frente TP2", "desde": f"Est. {t2d}", "hasta": f"Est. {t2h}", "color": "#7F77DD"})
    if frentes_06:
        html_frentes(frentes_06)

    with st.expander("Ver detalle técnico"):
        st.plotly_chart(build_figure_cv006(df_06, img_tecnica_b64),
                        use_container_width=True, key="gr06")

# ── CV007 ────────────────────────────────────────────────────
with c3:
    html_correa_card_header("CV007", True,
                            met_07["metros_t"], met_07["metros_s"], met_07["total_s"])
    html_progress_bar("🔴 Troncal",   100.0, "#E24B4A",
                      met_07["metros_t"], met_07["metros_t"], met_07["factor_t"])
    html_progress_bar("🟣 Sensitiva", 100.0, "#639922",
                      met_07["metros_s"], met_07["total_s"], met_07["factor_s"])
    html_frentes([{"label": "Frente único", "desde": "Est. 3", "hasta": "Est. 842", "color": "#639922"}])

    with st.expander("Ver detalle técnico"):
        st.plotly_chart(build_figure_cv007(df_07, img_tecnica_b64),
                        use_container_width=True, key="gr07")

# ── Historial ────────────────────────────────────────────────
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
html_section_title("Historial de registros de campo")

df_hist = leer_historial_reciente(limit=50)
if not df_hist.empty and "created_at" in df_hist.columns:
    if "created_at_dt" not in df_hist.columns:
        df_hist["created_at_dt"] = pd.to_datetime(df_hist["created_at"], utc=True).dt.tz_convert("America/Santiago")
    df_hist["Fecha registro"] = df_hist["created_at_dt"].dt.strftime("%d-%m-%Y %H:%M")

html_hist_table(df_hist)

# ============================================================
# 10. SIDEBAR — FORMULARIO DE REGISTRO
# ============================================================
with st.sidebar:
    st.markdown("""
    <div style="padding:8px 0 10px">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.3px;
                  color:rgba(255,255,255,0.3);margin-bottom:3px">Panel de operación</div>
      <div style="font-size:14px;font-weight:500;color:#F0F2F5">Registro de datos</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Estado rápido**")
    for cid, pct_s_val in [
        ("CV005", met_05["pct_s"]),
        ("CV006", met_06["pct_s"]),
        ("CV007", 100.0),
    ]:
        color_bar = "#639922" if pct_s_val >= 100 else "#7F77DD"
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.07);
                    border-radius:8px;padding:8px 11px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;margin-bottom:5px">
            <span style="font-size:11px;font-weight:500;color:#F0F2F5">{cid}</span>
            <span style="font-size:10px;color:rgba(255,255,255,0.35)">Sensitiva {pct_s_val:.1f}%</span>
          </div>
          <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:4px;overflow:hidden">
            <div style="width:{min(pct_s_val,100):.1f}%;background:{color_bar};height:100%;border-radius:99px"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── CV005 ────────────────────────────────────────────
    with st.expander("➕ Ingreso datos CV005"):
        with st.form(key="form_CV005"):
            op = st.text_input("Operador", key="op_CV005", placeholder="Nombre")
            tipo_evento = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV005")
            niv = st.selectbox("Tipo de fibra", list(NIVELES.keys()),
                               format_func=lambda x: NIVELES[x]["nombre"], key="niv_CV005")
            frente_sel = st.radio(
                "Frente de trabajo",
                ["TP1 → Centro (Est. 3823 → 2000)", "EM → Centro (Est. 1 → 2000)"],
                key="frente_CV005"
            )
            frente_key = "tp1" if "TP1" in frente_sel else "em"

            if frente_key == "tp1":
                d = st.number_input("Desde Est. (punta frente TP1)", min_value=2000, max_value=3823,
                                    value=3823, step=1, key="d_CV005_tp1", format="%d")
                h = st.number_input("Hasta Est. (avance actual)",    min_value=2000, max_value=3823,
                                    value=2000, step=1, key="h_CV005_tp1", format="%d")
            else:
                d = st.number_input("Desde Est. (punta frente EM)", min_value=1, max_value=2000,
                                    value=1,    step=1, key="d_CV005_em", format="%d")
                h = st.number_input("Hasta Est. (avance actual)",   min_value=1, max_value=2000,
                                    value=2000, step=1, key="h_CV005_em", format="%d")

            est_diff = abs(int(h) - int(d))
            factor   = FACTORES["CV005"]["troncal"] if niv == 0 else FACTORES["CV005"]["sensitiva"]
            st.caption(f"📏 {est_diff} est × {factor:.2f} m/est = **{est_diff * factor:,.1f} m**")
            nota = st.text_input("Observación", key="nota_CV005", placeholder="Ej: fusión completada")

            if st.form_submit_button("💾 Guardar registro CV005"):
                if not op.strip():
                    st.error("Ingresa el nombre del operador.")
                elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, "CV005", frente_key):
                    st.success(f"✅ Guardado — CV005 / frente {frente_key.upper()}")
                    st.rerun()

    # ── CV006 ────────────────────────────────────────────
    with st.expander("➕ Ingreso datos CV006"):
        with st.form(key="form_CV006"):
            op = st.text_input("Operador", key="op_CV006", placeholder="Nombre")
            tipo_evento = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV006")
            niv = st.selectbox("Tipo de fibra", list(NIVELES.keys()),
                               format_func=lambda x: NIVELES[x]["nombre"], key="niv_CV006")
            frente_sel = st.radio(
                "Frente de trabajo",
                ["TP1 → Centro (3B Carga → Est. 1845)", "TP2 → Centro (Est. 3526 → 1846)"],
                key="frente_CV006"
            )
            frente_key = "tp1" if "TP1" in frente_sel else "tp2"

            if frente_key == "tp1":
                d = st.number_input("Desde Est.", min_value=-3, max_value=1845,
                                    value=-3,  step=1, key="d_CV006_tp1", format="%d")
                h = st.number_input("Hasta Est.", min_value=-3, max_value=1845,
                                    value=1845, step=1, key="h_CV006_tp1", format="%d")
            else:
                d = st.number_input("Desde Est.", min_value=1846, max_value=3526,
                                    value=3526, step=1, key="d_CV006_tp2", format="%d")
                h = st.number_input("Hasta Est.", min_value=1846, max_value=3526,
                                    value=1846, step=1, key="h_CV006_tp2", format="%d")

            est_diff = abs(int(h) - int(d))
            factor   = FACTORES["CV006"]["troncal"] if niv == 0 else FACTORES["CV006"]["sensitiva"]
            st.caption(f"📏 {est_diff} est × {factor:.2f} m/est = **{est_diff * factor:,.1f} m**")
            nota = st.text_input("Observación", key="nota_CV006", placeholder="Ej: fusión completada")

            if st.form_submit_button("💾 Guardar registro CV006"):
                if not op.strip():
                    st.error("Ingresa el nombre del operador.")
                elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, "CV006", frente_key):
                    st.success(f"✅ Guardado — CV006 / frente {frente_key.upper()}")
                    st.rerun()

    # ── CV007 ────────────────────────────────────────────
    with st.expander("➕ Ingreso datos CV007"):
        with st.form(key="form_CV007"):
            op = st.text_input("Operador", key="op_CV007", placeholder="Nombre")
            tipo_evento = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV007")
            niv = st.selectbox("Tipo de fibra", list(NIVELES.keys()),
                               format_func=lambda x: NIVELES[x]["nombre"], key="niv_CV007")
            r = EST_RANGES["CV007"]
            d = st.number_input("Desde Est.", min_value=r["min"], max_value=r["max"],
                                value=r["min"], key="d_CV007")
            h = st.number_input("Hasta Est.", min_value=r["min"], max_value=r["max"],
                                value=r["max"], key="h_CV007")

            est_diff = abs(int(h) - int(d))
            factor   = FACTORES["CV007"]["troncal"] if niv == 0 else FACTORES["CV007"]["sensitiva"]
            st.caption(f"📏 {est_diff} est × {factor:.2f} m/est = **{est_diff * factor:,.1f} m**")
            nota = st.text_input("Observación", key="nota_CV007", placeholder="Ej: sin novedades")

            if st.form_submit_button("💾 Guardar registro CV007"):
                if not op.strip():
                    st.error("Ingresa el nombre del operador.")
                elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, "CV007", "unico"):
                    st.success("✅ Guardado — CV007")
                    st.rerun()
