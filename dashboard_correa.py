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
    "CV006": {"min": -3, "max": 3526, "total": 3529, "centro": None},
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
    0: {"nombre": "Fibra Óptica Troncal",               "color": "#E24B4A", "glow": "rgba(226,75,74,0.18)"},
    5: {"nombre": "Fibra Óptica Sensitiva Monitoreada", "color": "#7F77DD", "glow": "rgba(127,119,221,0.18)"},
}

# Frentes de avance definidos por correa
# CV005: frente "tp1" avanza Est.3823→2000 (decrece), frente "em" avanza Est.1→2000 (crece)
# CV006: frente "tp1" avanza Est.-3→1845 (crece),   frente "tp2" avanza Est.3526→1846 (decrece)
# CV007: un solo frente
FRENTES = {
    "CV005": ["tp1", "em"],
    "CV006": ["tp1", "tp2"],
    "CV007": ["unico"],
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
    frente: str,
) -> bool:
    """
    Guarda un nuevo registro en Supabase SIN borrar los anteriores.
    El campo 'frente' identifica desde qué extremo avanza el tramo.
    Cada INSERT es un nuevo evento histórico independiente.
    """
    try:
        nuevo = {
            "operador":       operador,
            "estacion_desde": int(desde),
            "estacion_hasta": int(hasta),
            "nivel":          int(nivel),
            "nota":           nota,
            "tipo_evento":    tipo_evento,
            "correa_id":      correa_id,
            "frente":         frente,          # campo nuevo — asegúrate de tenerlo en Supabase
        }
        supabase.table("eventos_correa").insert(nuevo).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar en Supabase: {e}")
        return False


def leer_historial_reciente(limit: int = 100) -> pd.DataFrame:
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

def obtener_tramo_activo(df: pd.DataFrame, nivel: int, frente: str) -> tuple[int | None, int | None]:
    """
    Del historial de una correa/nivel/frente, devuelve el tramo más reciente
    (el último registro por created_at).  Retorna (desde, hasta) o (None, None).
    """
    if df.empty:
        return None, None

    sub = df[(df["nivel"].astype(int) == nivel)]
    if "frente" in sub.columns:
        sub = sub[sub["frente"] == frente]

    if sub.empty:
        return None, None

    # Ordenar por fecha descendente y tomar el más reciente
    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at", ascending=False)

    row = sub.iloc[0]
    return int(row["estacion_desde"]), int(row["estacion_hasta"])


def calcular_metraje(df: pd.DataFrame, correa_id: str) -> dict:
    """
    Calcula metros y porcentajes de troncal y sensitiva para una correa.
    Usa el tramo ACTIVO más reciente por cada frente + nivel (sin sumar duplicados).
    """
    ft = FACTORES[correa_id]["troncal"]
    fs = FACTORES[correa_id]["sensitiva"]
    metros_t = 0.0
    metros_s = 0.0

    frentes = FRENTES.get(correa_id, ["unico"])

    for frente in frentes:
        for nivel, factor in [(0, ft), (5, fs)]:
            d, h = obtener_tramo_activo(df, nivel, frente)
            if d is not None and h is not None:
                metros = abs(h - d) * factor
                if nivel == 0:
                    metros_t += metros
                else:
                    metros_s += metros

    # Si la tabla aún no tiene columna 'frente', fallback: sumar todos los registros únicos
    if "frente" not in (df.columns if not df.empty else pd.Index([])):
        metros_t = 0.0
        metros_s = 0.0
        if not df.empty:
            for _, row in df.iterrows():
                cant = abs(int(row["estacion_hasta"]) - int(row["estacion_desde"]))
                if int(row["nivel"]) == 0:
                    metros_t += cant * ft
                elif int(row["nivel"]) == 5:
                    metros_s += cant * fs

    mts_t_real = {"CV005": 5916.0, "CV006": 5876.0, "CV007": 1339.0}
    total_s = SENSITIVA_TOTAL_MTS[correa_id]
    pct_s = min((metros_s / total_s) * 100, 100.0) if total_s > 0 else 0.0

    return {
        "metros_t": mts_t_real.get(correa_id, metros_t),
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


def label_estacion(est: int, correa_id: str) -> str:
    if correa_id == "CV006":
        return MAPEO_NUM_A_LETRA.get(int(est), str(est))
    return str(est)


def segmentos_activos(df: pd.DataFrame, nivel: int, frentes: list[str]) -> list[dict]:
    """
    Para una correa, nivel y lista de frentes, devuelve la lista de
    segmentos a dibujar: el más reciente por cada frente.
    """
    segs = []
    for frente in frentes:
        d, h = obtener_tramo_activo(df, nivel, frente)
        if d is not None and h is not None:
            segs.append({"desde": d, "hasta": h, "frente": frente})
    # Fallback: si no hay columna 'frente', tomar todos los registros
    if not segs and not df.empty and "frente" not in df.columns:
        sub = df[df["nivel"].astype(int) == nivel]
        for _, row in sub.iterrows():
            segs.append({"desde": int(row["estacion_desde"]), "hasta": int(row["estacion_hasta"]), "frente": "unico"})
    return segs

# ============================================================
# 6. ESTILOS GLOBALES
# ============================================================

def apply_styles(img_fondo_b64):
    css_base = """
    <style>
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    [data-testid="stAppViewContainer"] {
        background-color: #0D1117;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }
    [data-testid="stSidebar"] {
        background: rgba(13, 17, 26, 0.97) !important;
        border-right: 0.5px solid rgba(255,255,255,0.08);
    }
    [data-testid="stMainBlockContainer"] {
        background: rgba(13, 17, 26, 0.82);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-top: 0.5rem;
    }
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
    [data-testid="stMetric"] {
        background: rgba(255,255,255,0.04);
        border: 0.5px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 12px 16px;
    }
    [data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 500 !important; }
    [data-testid="stMetricLabel"] { font-size: 12px !important; color: rgba(255,255,255,0.5) !important; }
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
    .stAlert { border-radius: 8px; font-size: 13px; }
    hr { border-color: rgba(255,255,255,0.08) !important; }
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

def _add_segmento(fig, xd, xh, niv, row, correa_id, label_d=None, label_h=None):
    """Agrega glow + línea de un segmento al figure."""
    md = estacion_a_metros(xd, correa_id, niv)
    mh = estacion_a_metros(xh, correa_id, niv)
    ld = label_d or str(xd)
    lh = label_h or str(xh)
    op  = row.get("operador", "—") if isinstance(row, dict) else row.get("operador", "—")
    nota = row.get("nota", "—") if isinstance(row, dict) else row.get("nota", "—")

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


def build_figure_cv005(df: pd.DataFrame, img_b64) -> go.Figure:
    """CV005: eje X transformado — 0 = Centro (Est. 2000).
    Dos frentes: tp1 (3823→2000) y em (1→2000), ambos se dibujan."""
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
        # Para cada combinación nivel+frente, tomar el registro más reciente
        for niv in [0, 5]:
            for frente in ["tp1", "em"]:
                d, h = obtener_tramo_activo(df, niv, frente)
                if d is None:
                    continue
                # Recuperar datos del registro más reciente para hover
                sub = df[df["nivel"].astype(int) == niv]
                if "frente" in sub.columns:
                    sub = sub[sub["frente"] == frente]
                if not sub.empty and "created_at" in sub.columns:
                    sub = sub.sort_values("created_at", ascending=False)
                row_data = sub.iloc[0].to_dict() if not sub.empty else {}

                xd, xh = tx(d), tx(h)
                _add_segmento(fig, xd, xh, niv, row_data, "CV005", str(d), str(h))

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


def build_figure_cv006(df: pd.DataFrame, img_b64) -> go.Figure:
    """CV006: eje X directo (−3 a 3526). Dos frentes: tp1 (-3→1845) y tp2 (3526→1846)."""
    fig = go.Figure()

    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y",
            x=-3, y=-0.5, sizex=3530, sizey=2.5,
            sizing="stretch", opacity=0.85, layer="below"
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


def build_figure_cv007(df: pd.DataFrame, img_b64) -> go.Figure:
    """CV007: eje X directo (3 a 842). Un solo frente."""
    fig = go.Figure()

    if img_b64:
        fig.add_layout_image(dict(
            source=f"data:image/png;base64,{img_b64}",
            xref="x", yref="y",
            x=3, y=-0.5, sizex=839 * 2, sizey=2.5,
            sizing="stretch", opacity=0.85, layer="below"
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


def render_progress_bar(label, pct, color, metros, total, factor):
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


def render_kpi_card(icon, label, value, sub, color="#378ADD"):
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

def get_base64_img(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


img_tecnica_b64 = get_base64_img("correa_tecnica.png")
img_fondo_b64   = get_base64_img("fondo_pantalla.jpeg")

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
                   display:inline-block"></span>
      <span style="font-size:12px;color:rgba(255,255,255,0.5)">Sistema en línea</span>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 11. LEER DATOS
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

with tab05:
    st.markdown("**Estado actual — CV005**")
    st.info("TP1 (Est. 3823) → Centro (Est. 2000) ← EM (Est. 1) · Troncal 100% completada")
    col_fig, col_met = st.columns([4, 1])
    with col_fig:
        st.plotly_chart(build_figure_cv005(df_05, img_tecnica_b64), use_container_width=True, key="gr05")
    with col_met:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_progress_bar("🔴 Troncal", met_05["pct_t"], "#E24B4A",
                            met_05["metros_t"], met_05["metros_t"], met_05["factor_t"])
        render_progress_bar("🟣 Sensitiva", met_05["pct_s"], "#7F77DD",
                            met_05["metros_s"], met_05["total_s"], met_05["factor_s"])

with tab06:
    st.markdown("**Estado actual — CV006**")
    st.info("3B Carga (TP1) → Centro (Est. 1845) | (Est. 1846) → TP2 (Est. 3526) · Troncal 100% completada")
    col_fig, col_met = st.columns([4, 1])
    with col_fig:
        st.plotly_chart(build_figure_cv006(df_06, img_tecnica_b64), use_container_width=True, key="gr06")
    with col_met:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_progress_bar("🔴 Troncal", met_06["pct_t"], "#E24B4A",
                            met_06["metros_t"], met_06["metros_t"], met_06["factor_t"])
        render_progress_bar("🟣 Sensitiva", met_06["pct_s"], "#7F77DD",
                            met_06["metros_s"], met_06["total_s"], met_06["factor_s"])

with tab07:
    st.markdown("**Estado actual — CV007** ✅ 100% completada")
    st.success("TP2 (Est. 3) → Shuttler (Est. 842) · Troncal 1,339 m · Sensitiva 14,568 m · Todo desplegado")
    col_fig, col_met = st.columns([4, 1])
    with col_fig:
        st.plotly_chart(build_figure_cv007(df_07, img_tecnica_b64), use_container_width=True, key="gr07")
    with col_met:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_progress_bar("🔴 Troncal", 100.0, "#E24B4A",
                            met_07["metros_t"], met_07["metros_t"], met_07["factor_t"])
        render_progress_bar("🟣 Sensitiva", 100.0, "#7F77DD",
                            met_07["metros_s"], met_07["total_s"], met_07["factor_s"])

# ============================================================
# 14. HISTORIAL CONSOLIDADO
# ============================================================
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.markdown("### 📋 Historial consolidado de registros de campo")

df_hist = leer_historial_reciente(limit=100)

if not df_hist.empty:
    cols_mostrar = {}
    if "correa_id"      in df_hist.columns: cols_mostrar["correa_id"]      = "Correa"
    if "frente"         in df_hist.columns: cols_mostrar["frente"]          = "Frente"
    if "tipo_evento"    in df_hist.columns: cols_mostrar["tipo_evento"]     = "Tipo de evento"
    if "operador"       in df_hist.columns: cols_mostrar["operador"]        = "Operador"
    if "estacion_desde" in df_hist.columns: cols_mostrar["estacion_desde"]  = "Desde Est."
    if "estacion_hasta" in df_hist.columns: cols_mostrar["estacion_hasta"]  = "Hasta Est."
    if "nivel"          in df_hist.columns:
        df_hist["nivel_nombre"] = df_hist["nivel"].apply(
            lambda x: NIVELES.get(int(x), {"nombre": str(x)})["nombre"]
        )
        cols_mostrar["nivel_nombre"] = "Tipo fibra"
    if "nota"           in df_hist.columns: cols_mostrar["nota"]            = "Observación"

    if "created_at" in df_hist.columns:
        df_hist["created_at_dt"] = pd.to_datetime(df_hist["created_at"], utc=True).dt.tz_convert("America/Santiago")
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

    # Resumen rápido
    st.markdown("**Estado rápido**")
    for cid, met, pct_s_val in [
        ("CV005", met_05, met_05["pct_s"]),
        ("CV006", met_06, met_06["pct_s"]),
        ("CV007", met_07, 100.0),
    ]:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.08);
                    border-radius:8px;padding:9px 12px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;margin-bottom:5px">
            <span style="font-size:12px;font-weight:500;color:#F0F2F5">{cid}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.4)">Sensitiva {pct_s_val:.1f}%</span>
          </div>
          <div style="background:rgba(255,255,255,0.07);border-radius:99px;height:5px;overflow:hidden">
            <div style="width:{min(pct_s_val,100):.1f}%;background:#7F77DD;height:100%;border-radius:99px"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── CV005 ────────────────────────────────────────────────
    with st.expander("➕ Ingreso datos CV005"):
        with st.form(key="form_CV005"):
            op = st.text_input("Operador", key="op_CV005", placeholder="Nombre")
            tipo_evento = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV005")
            niv = st.selectbox("Tipo de fibra", list(NIVELES.keys()),
                               format_func=lambda x: NIVELES[x]["nombre"], key="niv_CV005")
            frente_cv005 = st.radio(
                "Frente de trabajo",
                ["TP1 → Centro (Est. 3823 → 2000)", "EM → Centro (Est. 1 → 2000)"],
                key="frente_CV005"
            )
            frente_key = "tp1" if "TP1" in frente_cv005 else "em"

            if frente_key == "tp1":
                # Avance desde 3823 hacia 2000 (la estación_desde será la punta del frente)
                d = st.number_input("Desde Est. (punta frente TP1)", min_value=2000, max_value=3823,
                                    value=3823, step=1, key="d_CV005_tp1", format="%d")
                h = st.number_input("Hasta Est. (centro)", min_value=2000, max_value=3823,
                                    value=2000, step=1, key="h_CV005_tp1", format="%d")
            else:
                # Avance desde 1 hacia 2000
                d = st.number_input("Desde Est. (punta frente EM)", min_value=1, max_value=2000,
                                    value=1, step=1, key="d_CV005_em", format="%d")
                h = st.number_input("Hasta Est. (centro)", min_value=1, max_value=2000,
                                    value=2000, step=1, key="h_CV005_em", format="%d")

            est_diff = abs(int(h) - int(d))
            factor = FACTORES["CV005"]["troncal"] if niv == 0 else FACTORES["CV005"]["sensitiva"]
            st.caption(f"📏 Estimado: {est_diff} est × {factor:.2f} m/est = **{est_diff * factor:,.1f} m**")
            nota = st.text_input("Observación", key="nota_CV005", placeholder="Ej: fusión completada")

            if st.form_submit_button("💾 Guardar registro CV005"):
                if not op.strip():
                    st.error("Ingresa el nombre del operador.")
                elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, "CV005", frente_key):
                    st.success(f"✅ Registro guardado — CV005 / frente {frente_key.upper()}")
                    st.rerun()

    # ── CV006 ────────────────────────────────────────────────
    with st.expander("➕ Ingreso datos CV006"):
        with st.form(key="form_CV006"):
            op = st.text_input("Operador", key="op_CV006", placeholder="Nombre")
            tipo_evento = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_CV006")
            niv = st.selectbox("Tipo de fibra", list(NIVELES.keys()),
                               format_func=lambda x: NIVELES[x]["nombre"], key="niv_CV006")
            frente_cv006 = st.radio(
                "Frente de trabajo",
                ["TP1 → Centro (3B Carga → Est. 1845)", "TP2 → Centro (Est. 3526 → 1846)"],
                key="frente_CV006"
            )
            frente_key = "tp1" if "TP1" in frente_cv006 else "tp2"

            if frente_key == "tp1":
                d = st.number_input("Desde Est.", min_value=-3, max_value=1845,
                                    value=-3, step=1, key="d_CV006_tp1", format="%d")
                h = st.number_input("Hasta Est.", min_value=-3, max_value=1845,
                                    value=1845, step=1, key="h_CV006_tp1", format="%d")
            else:
                d = st.number_input("Desde Est.", min_value=1846, max_value=3526,
                                    value=3526, step=1, key="d_CV006_tp2", format="%d")
                h = st.number_input("Hasta Est.", min_value=1846, max_value=3526,
                                    value=1846, step=1, key="h_CV006_tp2", format="%d")

            est_diff = abs(int(h) - int(d))
            factor = FACTORES["CV006"]["troncal"] if niv == 0 else FACTORES["CV006"]["sensitiva"]
            st.caption(f"📏 Estimado: {est_diff} est × {factor:.2f} m/est = **{est_diff * factor:,.1f} m**")
            nota = st.text_input("Observación", key="nota_CV006", placeholder="Ej: fusión completada")

            if st.form_submit_button("💾 Guardar registro CV006"):
                if not op.strip():
                    st.error("Ingresa el nombre del operador.")
                elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, "CV006", frente_key):
                    st.success(f"✅ Registro guardado — CV006 / frente {frente_key.upper()}")
                    st.rerun()

    # ── CV007 ────────────────────────────────────────────────
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
            factor = FACTORES["CV007"]["troncal"] if niv == 0 else FACTORES["CV007"]["sensitiva"]
            st.caption(f"📏 Estimado: {est_diff} est × {factor:.2f} m/est = **{est_diff * factor:,.1f} m**")
            nota = st.text_input("Observación", key="nota_CV007", placeholder="Ej: fusión completada")

            if st.form_submit_button("💾 Guardar registro CV007"):
                if not op.strip():
                    st.error("Ingresa el nombre del operador.")
                elif guardar_registro(op.strip(), d, h, niv, nota, tipo_evento, "CV007", "unico"):
                    st.success("✅ Registro guardado — CV007")
                    st.rerun()
