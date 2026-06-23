"""
Sistema de Monitoreo de Polines mediante Fibra Óptica
Dashboard principal — CV005 / CV006 / CV007
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
import base64
from datetime import datetime

# ============================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ============================================================
st.set_page_config(
    layout="wide",
    page_title="Monitoreo Fibra Óptica — CV",
    page_icon="🔴",
)

# ============================================================
# 2. CONSTANTES DE INGENIERÍA (valores reales de terreno)
# ============================================================

# Factores metros/estación por correa y tipo de fibra
FACTORES = {
    "CV005": {"troncal": 1.547, "sensitiva": 10.83},
    "CV006": {"troncal": 1.665, "sensitiva": 13.66},
    "CV007": {"troncal": 1.595, "sensitiva": 17.36},
}

# Rangos de estaciones por correa
EST_RANGES = {
    "CV005": {"min": 1,  "max": 3823, "total": 3822, "centro": 2000},
    "CV006": {"min": -3, "max": 3526, "total": 3529, "centro": 1845},
    "CV007": {"min": 3,  "max": 842,  "total": 839,  "centro": None},
}

# Metraje total estimado de sensitiva por correa (para % real)
SENSITIVA_TOTAL_MTS = {
    "CV005": 41402.0,
    "CV006": 48214.0,
    "CV007": 14568.0,
}

# Mapeo estaciones negativas CV006 ↔ etiquetas alfabéticas
MAPEO_NUM_A_LETRA = {-3: "3B Carga", -2: "2B Carga", -1: "1B Carga"}
MAPEO_LETRA_A_NUM = {v: k for k, v in MAPEO_NUM_A_LETRA.items()}

# Niveles de fibra: 0 = troncal, 5 = sensitiva
NIVELES = {
    0: {"nombre": "Fibra Óptica Troncal",            "color": "#E24B4A", "glow": "rgba(226,75,74,0.18)"},
    5: {"nombre": "Fibra Óptica Sensitiva Monitoreada", "color": "#7F77DD", "glow": "rgba(127,119,221,0.18)"},
}

# Tipos de evento para el formulario
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
# 4. FUNCIONES DE BASE DE DATOS
# ============================================================

def leer_datos(correa_id: str) -> pd.DataFrame:
    """Lee todos los eventos activos de una correa."""
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


def guardar_registro(
    operador: str,
    desde: int,
    hasta: int,
    nivel: int,
    nota: str,
    tipo_evento: str,
    correa_id: str,
) -> bool:
    """
    Guarda un nuevo registro en Supabase.
    CV006 mantiene registros separados por tramo (<=1845 y >1845).
    """
    try:
        # Borrar registro anterior del mismo nivel/tramo
        if correa_id == "CV006":
            if desde <= 1845:
                supabase.table("eventos_correa").delete() \
                    .eq("correa_id", correa_id).eq("nivel", nivel) \
                    .lte("estacion_desde", 1845).execute()
            else:
                supabase.table("eventos_correa").delete() \
                    .eq("correa_id", correa_id).eq("nivel", nivel) \
                    .gt("estacion_desde", 1845).execute()
        else:
            supabase.table("eventos_correa").delete() \
                .eq("correa_id", correa_id).eq("nivel", nivel).execute()

        nuevo = {
            "operador":      operador,
            "estacion_desde": int(desde),
            "estacion_hasta": int(hasta),
            "nivel":          int(nivel),
            "nota":           nota,
            "tipo_evento":    tipo_evento,
            "correa_id":      correa_id,
        }
        supabase.table("eventos_correa").insert(nuevo).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar en Supabase: {e}")
        return False


def leer_historial_reciente(limit: int = 50) -> pd.DataFrame:
    """Lee el historial consolidado de las 3 correas, ordenado por fecha."""
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
# 5. FUNCIONES DE CÁLCULO
# ============================================================

def calcular_metraje(df: pd.DataFrame, correa_id: str) -> dict:
    """
    Calcula metros y porcentajes de troncal y sensitiva para una correa.
    Retorna dict con claves: metros_t, metros_s, pct_t, pct_s
    """
    metros_t = 0.0
    metros_s = 0.0
    ft = FACTORES[correa_id]["troncal"]
    fs = FACTORES[correa_id]["sensitiva"]

    if not df.empty:
        for _, row in df.iterrows():
            cant = abs(int(row["estacion_hasta"]) - int(row["estacion_desde"])) * 1
            # Incluir ambos extremos
            cant = abs(int(row["estacion_hasta"]) - int(row["estacion_desde"]))
            if int(row["nivel"]) == 0:
                metros_t += cant * ft
            elif int(row["nivel"]) == 5:
                metros_s += cant * fs

    # Troncal: longitud fija real
    mts_t_real = {"CV005": 5916.0, "CV006": 5876.0, "CV007": 1339.0}
    pct_t = 100.0 if correa_id in mts_t_real else (metros_t / (EST_RANGES[correa_id]["total"] * ft) * 100)

    total_s = SENSITIVA_TOTAL_MTS[correa_id]
    pct_s = min((metros_s / total_s) * 100, 100.0) if total_s > 0 else 0.0

    return {
        "metros_t": mts_t_real.get(correa_id, metros_t),
        "metros_s": metros_s,
        "pct_t":    100.0,  # troncal siempre al 100% según datos de terreno
        "pct_s":    pct_s,
        "factor_t": ft,
        "factor_s": fs,
        "total_s":  total_s,
    }


def estacion_a_metros(estacion: int, correa_id: str, nivel: int) -> float:
    """Convierte número de estación a metros lineales desde el origen."""
    factor = FACTORES[correa_id]["troncal"] if nivel == 0 else FACTORES[correa_id]["sensitiva"]
    origen = EST_RANGES[correa_id]["min"]
    return abs(int(estacion) - origen) * factor


def label_estacion(est: int, correa_id: str) -> str:
    """Devuelve etiqueta legible de una estación."""
    if correa_id == "CV006":
        return MAPEO_NUM_A_LETRA.get(int(est), str(est))
    return str(est)

# ============================================================
# 6. ESTILOS GLOBALES
# ============================================================

def apply_styles(img_fondo_b64: str | None):
    css_base = """
    <style>
    /* Fuente y colores base */
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Fondo de página */
    [data-testid="stAppViewContainer"] {
        background-color: #0D1117;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }
    /* Sidebar oscura */
    [data-testid="stSidebar"] {
        background: rgba(13, 17, 26, 0.97) !important;
        border-right: 0.5px solid rgba(255,255,255,0.08);
    }
    /* Contenedor principal */
    [data-testid="stMainBlockContainer"] {
        background: rgba(13, 17, 26, 0.82);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-top: 0.5rem;
    }
    /* Tabs de Streamlit */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.04);
        border-radius: 8px;
        padding: 3px;
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: rgba(255,255,255,0.55);
        font-size: 13px;
        padding: 6px 18px;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(55, 138, 221, 0.18) !important;
        color: #378ADD !important;
        font-weight: 500;
    }
    /* Métricas */
    [data-testid="stMetric"] {
        background: rgba(255,255,255,0.04);
        border: 0.5px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 12px 16px;
    }
    [data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 500 !important; }
    [data-testid="stMetricLabel"] { font-size: 12px !important; color: rgba(255,255,255,0.5) !important; }
    /* Botones */
    .stButton > button {
        background: rgba(55, 138, 221, 0.15);
        border: 0.5px solid rgba(55, 138, 221, 0.4);
        color: #378ADD;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        width: 100%;
        padding: 8px 0;
    }
    .stButton > button:hover {
        background: rgba(55, 138, 221, 0.25);
        border-color: rgba(55, 138, 221, 0.65);
    }
    /* Info boxes */
    .stAlert { border-radius: 8px; font-size: 13px; }
    /* Divisor sidebar */
    hr { border-color: rgba(255,255,255,0.08) !important; }
    /* DataFrame */
    [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    </style>
    """
    if img_fondo_b64:
        bg_extra = f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: url("data:image/jpeg;base64,{img_fondo_b64}");
        }}
        </style>
        """
        st.markdown(bg_extra, unsafe_allow_html=True)
    st.markdown(css_base, unsafe_allow_html=True)

# ============================================================
# 7. COMPONENTES DE VISUALIZACIÓN
# ============================================================

def build_figure_cv005(df: pd.DataFrame, img_b64: str | None) -> go.Figure:
    """Figura Plotly para CV005. Eje X transformado: 0 = Centro (Est. 2000)."""
    def tx(est):
        e = int(est)
        return -(e - 2000) if e >= 2000 else (2000 - e)

    fig = go.Figure()

    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y",
            x=-1823, y=-0.5, sizex=3823, sizey=2.5,
            sizing="stretch", opacity=0.85, layer="below"
        ))

    if not df.empty:
        for _, fila in df.iterrows():
            try:
                niv  = int(fila["nivel"])
                d, h = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                xd, xh = tx(d), tx(h)
                md = estacion_a_metros(d, "CV005", niv)
                mh = estacion_a_metros(h, "CV005", niv)

                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines",
                    line=dict(color=NIVELES[niv]["glow"], width=14),
                    hoverinfo="skip", showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines+markers",
                    line=dict(color=NIVELES[niv]["color"], width=3),
                    marker=dict(size=7, color=NIVELES[niv]["color"]),
                    customdata=[[d, md, fila.get("operador","—"), fila.get("nota","—")],
                                [h, mh, fila.get("operador","—"), fila.get("nota","—")]],
                    hovertemplate=(
                        f"<b>{NIVELES[niv]['nombre']}</b><br>"
                        "📍 Estación: %{customdata[0]}<br>"
                        "📏 Posición: %{customdata[1]:.1f} m<br>"
                        "👷 Operador: %{customdata[2]}<br>"
                        "📝 %{customdata[3]}<extra></extra>"
                    ),
                    showlegend=False
                ))
            except Exception:
                pass

    fig.update_layout(
        xaxis=dict(
            tickvals=[-1823, -1000, 0, 1000, 1999],
            ticktext=["TP1 (3823)", "3000", "Centro (2000)", "1000", "EM (1)"],
            gridcolor="rgba(255,255,255,0.04)", color="rgba(255,255,255,0.5)",
        ),
        yaxis=dict(
            range=[-2.5, 7.5], dtick=5,
            tickvals=list(NIVELES.keys()),
            ticktext=[n["nombre"] for n in NIVELES.values()],
            color="rgba(255,255,255,0.5)",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=30, t=20, b=40),
        height=320,
    )
    return fig


def build_figure_cv006(df: pd.DataFrame, img_b64: str | None) -> go.Figure:
    """Figura Plotly para CV006. Eje X directo (−3 a 3526)."""
    fig = go.Figure()

    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y",
            x=-3, y=-0.5, sizex=3530, sizey=2.5,
            sizing="stretch", opacity=0.85, layer="below"
        ))

    if not df.empty:
        for _, fila in df.iterrows():
            try:
                niv = int(fila["nivel"])
                pts = sorted([int(fila["estacion_desde"]), int(fila["estacion_hasta"])])
                xd, xh = pts[0], pts[1]
                md = estacion_a_metros(xd, "CV006", niv)
                mh = estacion_a_metros(xh, "CV006", niv)
                ld = fila.get("est_desde_label", str(xd))
                lh = fila.get("est_hasta_label", str(xh))

                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines",
                    line=dict(color=NIVELES[niv]["glow"], width=14),
                    hoverinfo="skip", showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines+markers",
                    line=dict(color=NIVELES[niv]["color"], width=3),
                    marker=dict(size=7, color=NIVELES[niv]["color"]),
                    customdata=[[ld, md, fila.get("operador","—"), fila.get("nota","—")],
                                [lh, mh, fila.get("operador","—"), fila.get("nota","—")]],
                    hovertemplate=(
                        f"<b>{NIVELES[niv]['nombre']}</b><br>"
                        "📍 Estación: %{customdata[0]}<br>"
                        "📏 Posición: %{customdata[1]:.1f} m<br>"
                        "👷 Operador: %{customdata[2]}<br>"
                        "📝 %{customdata[3]}<extra></extra>"
                    ),
                    showlegend=False
                ))
            except Exception:
                pass

    fig.update_layout(
        xaxis=dict(
            range=[-10, 3540],
            tickvals=[-3, 1845, 1846, 3526],
            ticktext=["3B Carga (TP1)", "Centro (1845)", "Centro (1846)", "TP2 (3526)"],
            gridcolor="rgba(255,255,255,0.04)", color="rgba(255,255,255,0.5)",
        ),
        yaxis=dict(
            range=[-2.5, 7.5], dtick=5,
            tickvals=list(NIVELES.keys()),
            ticktext=[n["nombre"] for n in NIVELES.values()],
            color="rgba(255,255,255,0.5)",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=30, t=20, b=40),
        height=320,
    )
    return fig


def build_figure_cv007(df: pd.DataFrame, img_b64: str | None) -> go.Figure:
    """Figura Plotly para CV007. Eje X directo (3 a 842)."""
    fig = go.Figure()

    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y",
            x=3, y=-0.5, sizex=839 * 2, sizey=2.5,
            sizing="stretch", opacity=0.85, layer="below"
        ))

    if not df.empty:
        for _, fila in df.iterrows():
            try:
                niv = int(fila["nivel"])
                pts = sorted([int(fila["estacion_desde"]), int(fila["estacion_hasta"])])
                xd, xh = pts[0], pts[1]
                md = estacion_a_metros(xd, "CV007", niv)
                mh = estacion_a_metros(xh, "CV007", niv)

                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines",
                    line=dict(color=NIVELES[niv]["glow"], width=14),
                    hoverinfo="skip", showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines+markers",
                    line=dict(color=NIVELES[niv]["color"], width=3),
                    marker=dict(size=7, color=NIVELES[niv]["color"]),
                    customdata=[[xd, md, fila.get("operador","—"), fila.get("nota","—")],
                                [xh, mh, fila.get("operador","—"), fila.get("nota","—")]],
                    hovertemplate=(
                        f"<b>{NIVELES[niv]['nombre']}</b><br>"
                        "📍 Estación: %{customdata[0]}<br>"
                        "📏 Posición: %{customdata[1]:.1f} m<br>"
                        "👷 Operador: %{customdata[2]}<br>"
                        "📝 %{customdata[3]}<extra></extra>"
                    ),
                    showlegend=False
                ))
            except Exception:
                pass

    fig.update_layout(
        xaxis=dict(
            range=[0, 855],
            tickvals=[3, 200, 400, 600, 842],
            ticktext=["TP2 (Est. 3)", "200", "400", "600", "Shuttler (Est. 842)"],
            gridcolor="rgba(255,255,255,0.04)", color="rgba(255,255,255,0.5)",
        ),
        yaxis=dict(
            range=[-2.5, 7.5], dtick=5,
            tickvals=list(NIVELES.keys()),
            ticktext=[n["nombre"] for n in NIVELES.values()],
            color="rgba(255,255,255,0.5)",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=30, t=20, b=40),
        height=320,
    )
    return fig


def render_progress_bar(label: str, pct: float, color: str, metros: float, total: float, factor: float):
    """Renderiza una barra de progreso personalizada con HTML."""
    pct_display = min(pct, 100.0)
    st.markdown(f"""
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:12px;color:rgba(255,255,255,0.6)">{label}</span>
        <span style="font-size:12px;font-weight:500;color:{color}">{pct:.2f}%</span>
      </div>
      <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:7px;overflow:hidden">
        <div style="width:{pct_display}%;background:{color};height:100%;border-radius:99px;
                    transition:width .4s ease"></div>
      </div>
      <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:3px">
        {metros:,.1f} m / ~{total:,.0f} m &nbsp;·&nbsp; {factor:.2f} m/est
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_kpi_card(icon: str, label: str, value: str, sub: str, color: str = "#378ADD"):
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.09);
                border-radius:10px;padding:14px 16px">
      <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:6px;display:flex;
                  align-items:center;gap:6px">
        <span style="width:8px;height:8px;border-radius:2px;background:{color};
                     display:inline-block"></span>{label}
      </div>
      <div style="font-size:22px;font-weight:500;color:#F0F2F5">{value}</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.35);margin-top:3px">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 8. CARGA DE IMÁGENES
# ============================================================

def get_base64_img(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


img_tecnica_b64  = get_base64_img("correa_tecnica.png")
img_fondo_b64    = get_base64_img("fondo_pantalla.jpeg")

# ============================================================
# 9. APLICAR ESTILOS
# ============================================================
apply_styles(img_fondo_b64)

# ============================================================
# 10. ENCABEZADO
# ============================================================
col_titulo, col_estado = st.columns([3, 1])
with col_titulo:
    st.markdown("""
    <div style="padding:4px 0 12px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;
                  color:rgba(255,255,255,0.35);margin-bottom:4px">
        Centro de Telemetría Térmica Avanzada
      </div>
      <h1 style="font-size:20px;font-weight:500;color:#F0F2F5;margin:0">
        Sistema de Monitoreo de Polines — Fibra Óptica
      </h1>
    </div>
    """, unsafe_allow_html=True)
with col_estado:
    st.markdown("""
    <div style="display:flex;justify-content:flex-end;align-items:center;gap:8px;padding-top:20px">
      <span style="width:7px;height:7px;border-radius:50%;background:#E24B4A;
                   display:inline-block;animation:none"></span>
      <span style="font-size:12px;color:rgba(255,255,255,0.5)">Sistema en línea</span>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 11. LEER DATOS DE LAS 3 CORREAS
# ============================================================
with st.spinner("Cargando datos desde Supabase…"):
    df_05 = leer_datos("CV005")
    df_06 = leer_datos("CV006")
    df_07 = leer_datos("CV007")

met_05 = calcular_metraje(df_05, "CV005")
met_06 = calcular_metraje(df_06, "CV006")
met_07 = calcular_metraje(df_07, "CV007")

# ============================================================
# 12. KPIs GLOBALES
# ============================================================
st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)

total_troncal = met_05["metros_t"] + met_06["metros_t"] + met_07["metros_t"]
total_sensitiva = met_05["metros_s"] + met_06["metros_s"] + met_07["metros_s"]
total_sensitiva_posible = sum(SENSITIVA_TOTAL_MTS.values())
pct_global_s = (total_sensitiva / total_sensitiva_posible * 100) if total_sensitiva_posible > 0 else 0

with k1:
    render_kpi_card("", "Troncal total desplegada",
                    f"{total_troncal:,.0f} m",
                    f"CV005: {met_05['metros_t']:,.0f} · CV006: {met_06['metros_t']:,.0f} · CV007: {met_07['metros_t']:,.0f}",
                    "#E24B4A")
with k2:
    render_kpi_card("", "Sensitiva total desplegada",
                    f"{total_sensitiva:,.0f} m",
                    f"CV005: {met_05['metros_s']:,.0f} · CV006: {met_06['metros_s']:,.0f} · CV007: {met_07['metros_s']:,.0f}",
                    "#7F77DD")
with k3:
    render_kpi_card("", "Correas troncal al 100%",
                    "3 / 3",
                    "CV005, CV006 y CV007 completas",
                    "#639922")
with k4:
    render_kpi_card("", "Cobertura sensitiva global",
                    f"{pct_global_s:.1f}%",
                    f"{total_sensitiva:,.0f} m de ~{total_sensitiva_posible:,.0f} m",
                    "#BA7517")

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ============================================================
# 13. PESTAÑAS POR CORREA
# ============================================================
tab05, tab06, tab07 = st.tabs(["📍 CV005", "📍 CV006", "📍 CV007 ✓"])

# ─── CV005 ─────────────────────────────────────────────────
with tab05:
    st.markdown("**Estado actual — CV005**")
    st.info("TP1 (Est. 3823) → Centro (Est. 2000) ← EM (Est. 1) · Troncal 100% completada")

    col_fig, col_met = st.columns([4, 1])
    with col_fig:
        fig05 = build_figure_cv005(df_05, img_tecnica_b64)
        st.plotly_chart(fig05, use_container_width=True, key="gr05")
    with col_met:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_progress_bar("🔴 Troncal", met_05["pct_t"], "#E24B4A",
                            met_05["metros_t"], met_05["metros_t"],
                            met_05["factor_t"])
        render_progress_bar("🟣 Sensitiva", met_05["pct_s"], "#7F77DD",
                            met_05["metros_s"], met_05["total_s"],
                            met_05["factor_s"])

# ─── CV006 ─────────────────────────────────────────────────
with tab06:
    st.markdown("**Estado actual — CV006**")
    st.info("3B Carga (TP1) → Centro (Est. 1845) | (Est. 1846) → TP2 (Est. 3526) · Troncal 100% completada")

    col_fig, col_met = st.columns([4, 1])
    with col_fig:
        fig06 = build_figure_cv006(df_06, img_tecnica_b64)
        st.plotly_chart(fig06, use_container_width=True, key="gr06")
    with col_met:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_progress_bar("🔴 Troncal", met_06["pct_t"], "#E24B4A",
                            met_06["metros_t"], met_06["metros_t"],
                            met_06["factor_t"])
        render_progress_bar("🟣 Sensitiva", met_06["pct_s"], "#7F77DD",
                            met_06["metros_s"], met_06["total_s"],
                            met_06["factor_s"])

# ─── CV007 ─────────────────────────────────────────────────
with tab07:
    st.markdown("**Estado actual — CV007** ✅ 100% completada")
    st.success("TP2 (Est. 3) → Shuttler (Est. 842) · Troncal 1,339 m · Sensitiva 14,568 m · Todo desplegado")

    col_fig, col_met = st.columns([4, 1])
    with col_fig:
        fig07 = build_figure_cv007(df_07, img_tecnica_b64)
        st.plotly_chart(fig07, use_container_width=True, key="gr07")
    with col_met:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_progress_bar("🔴 Troncal", 100.0, "#E24B4A",
                            met_07["metros_t"], met_07["metros_t"],
                            met_07["factor_t"])
        render_progress_bar("🟣 Sensitiva", 100.0, "#7F77DD",
                            met_07["metros_s"], met_07["total_s"],
                            met_07["factor_s"])

# ============================================================
# 14. HISTORIAL CONSOLIDADO
# ============================================================
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.markdown("### 📋 Historial consolidado de registros de campo")

df_hist = leer_historial_reciente(limit=100)

if not df_hist.empty:
    cols_mostrar = {}
    if "correa_id" in df_hist.columns:        cols_mostrar["correa_id"] = "Correa"
    if "tipo_evento" in df_hist.columns:      cols_mostrar["tipo_evento"] = "Tipo de evento"
    if "operador" in df_hist.columns:         cols_mostrar["operador"] = "Operador"
    if "estacion_desde" in df_hist.columns:   cols_mostrar["estacion_desde"] = "Desde Est."
    if "estacion_hasta" in df_hist.columns:   cols_mostrar["estacion_hasta"] = "Hasta Est."
    if "nivel" in df_hist.columns:
        df_hist["nivel_nombre"] = df_hist["nivel"].apply(
            lambda x: NIVELES.get(int(x), {"nombre": str(x)})["nombre"]
        )
        cols_mostrar["nivel_nombre"] = "Tipo fibra"
    if "nota" in df_hist.columns:             cols_mostrar["nota"] = "Observación"

    if "created_at_dt" in df_hist.columns:
        df_hist["Fecha registro"] = df_hist["created_at_dt"].dt.strftime("%d-%m-%Y %H:%M")
        cols_mostrar["Fecha registro"] = "Fecha registro"

    df_view = df_hist[[c for c in cols_mostrar if c in df_hist.columns]].rename(columns=cols_mostrar)
    st.dataframe(df_view, use_container_width=True, hide_index=True)
else:
    st.info("Sin registros en la base de datos aún.")

# ============================================================
# 15. SIDEBAR — FORMULARIO DE REGISTRO
# ============================================================
with st.sidebar:
    st.markdown("""
    <div style="padding:12px 0 8px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;
                  color:rgba(255,255,255,0.35);margin-bottom:2px">Panel de operación</div>
      <div style="font-size:15px;font-weight:500;color:#F0F2F5">Registro de datos</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Resumen rápido de estado ────────────────────────────
    st.markdown("**Estado rápido**")
    for cid, met, pct_s_val in [
        ("CV005", met_05, met_05["pct_s"]),
        ("CV006", met_06, met_06["pct_s"]),
        ("CV007", met_07, 100.0),
    ]:
        color_s = "#7F77DD"
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.08);
                    border-radius:8px;padding:9px 12px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;margin-bottom:5px">
            <span style="font-size:12px;font-weight:500;color:#F0F2F5">{cid}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.4)">Sensitiva {pct_s_val:.1f}%</span>
          </div>
          <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:5px;overflow:hidden">
            <div style="width:{min(pct_s_val,100):.1f}%;background:{color_s};height:100%;border-radius:99px"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Formularios por correa ──────────────────────────────
    for correa_id, label_info in [
        ("CV005", "Est. 1 a 3823"),
        ("CV006", "3B Carga (−3) a 3526"),
        ("CV007", "Est. 3 a 842"),
    ]:
        with st.expander(f"➕ Ingreso datos {correa_id}"):
            with st.form(key=f"form_{correa_id}"):
                op = st.text_input("Operador", key=f"op_{correa_id}", placeholder="Nombre")

                tipo_evento = st.selectbox(
                    "Tipo de evento",
                    TIPOS_EVENTO,
                    key=f"tipo_{correa_id}"
                )

                niv = st.selectbox(
                    "Tipo de fibra",
                    list(NIVELES.keys()),
                    format_func=lambda x: NIVELES[x]["nombre"],
                    key=f"niv_{correa_id}"
                )

                r = EST_RANGES[correa_id]

                if correa_id == "CV006":
                    frente = st.radio(
                        "Frente de trabajo",
                        ["3B Carga → Centro (1845)", "1846 → TP2 (3526)"],
                        key=f"frente_{correa_id}"
                    )
                    if "3B Carga" in frente:
                        d = st.number_input("Desde Est.", min_value=-3, max_value=1845,
                                            value=-3, step=1, key=f"d_{correa_id}_a", format="%d")
                        h = st.number_input("Hasta Est.", min_value=-3, max_value=1845,
                                            value=1845, step=1, key=f"h_{correa_id}_a", format="%d")
                    else:
                        d = st.number_input("Desde Est.", min_value=1846, max_value=3526,
                                            value=1846, step=1, key=f"d_{correa_id}_b", format="%d")
                        h = st.number_input("Hasta Est.", min_value=1846, max_value=3526,
                                            value=3526, step=1, key=f"h_{correa_id}_b", format="%d")
                else:
                    d = st.number_input("Desde Est.", min_value=r["min"], max_value=r["max"],
                                        value=r["min"], key=f"d_{correa_id}")
                    h = st.number_input("Hasta Est.", min_value=r["min"], max_value=r["max"],
                                        value=r["max"], key=f"h_{correa_id}")

                # Preview de metraje
                est_diff = abs(int(h) - int(d))
                factor = FACTORES[correa_id]["troncal"] if niv == 0 else FACTORES[correa_id]["sensitiva"]
                mts_est = est_diff * factor
                st.caption(f"📏 Estimado: {est_diff} est × {factor:.2f} m/est = **{mts_est:,.1f} m**")

                nota = st.text_input("Observación", key=f"nota_{correa_id}",
                                     placeholder="Ej: fusión completada, sin novedades")

                if st.form_submit_button(f"💾 Guardar registro {correa_id}"):
                    if not op.strip():
                        st.error("Ingresa el nombre del operador.")
                    elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, correa_id):
                        st.success(f"✅ Registro guardado — {correa_id}")
                        st.rerun()
