import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
import base64

# 1. CONFIGURACIÓN DE PÁGINA (ESTABLECIDA ANTES DE CUALQUIER OTRA COSA)
st.set_page_config(layout="wide", page_title="Sistema Monitoreo Global - CV")

# 2. CONEXIÓN A SUPABASE
SUPABASE_URL = "https://aumkuyciwmeevnwtsvpy.supabase.co"
SUPABASE_KEY = "sb_publishable_5Iq0mHkNsetilyAFFQo1tw_-dth1liU"

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_supabase()
except Exception:
    st.error("Error de conexión con la base de datos Supabase.")

MAPEO_LETRAS_A_NUM = {"3B Carga": -3, "2B Carga": -2, "1B Carga": -1}
MAPEO_NUM_A_LETRAS = {-3: "3B Carga", -2: "2B Carga", -1: "1B Carga"}

# DICCIONARIO EXCLUSIVO: Solo los dos niveles validados con colores de neón intensos
DICC_NIVELES = {
    0: {"nombre": "Fibra Óptica Troncal", "color": "#FF0000", "glow": "rgba(255, 0, 0, 0.3)"},
    5: {"nombre": "Fibra Óptica Sensitiva monitored", "color": "#E066FF", "glow": "rgba(224, 102, 255, 0.3)"}
}

# 3. FUNCIONES DE BASE DE DATOS Y CONVERSIÓN
def leer_datos(correa_id):
    try:
        response = supabase.table("eventos_correa").select("*").eq("correa_id", correa_id).in_("nivel", [0, 5]).execute()
        df = pd.DataFrame(response.data)
        if not df.empty and correa_id == "CV006":
            df["estacion_desde"] = df["estacion_desde"].apply(lambda x: MAPEO_NUM_A_LETRAS.get(int(x), str(x)))
            df["estacion_hasta"] = df["estacion_hasta"].apply(lambda x: MAPEO_NUM_A_LETRAS.get(int(x), str(x)))
        return df
    except Exception:
        return pd.DataFrame()

def guardar_registro(operador, desde, hasta, nivel, nota, correa_id):
    val_desde = MAPEO_LETRAS_A_NUM.get(desde, desde)
    val_hasta = MAPEO_LETRAS_A_NUM.get(hasta, hasta)
    
    try:
        if correa_id == "CV006":
            if int(val_desde) <= 1845:
                supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).lte("estacion_desde", 1845).execute()
            else:
                supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).gt("estacion_desde", 1845).execute()
        else:
            supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).execute()
    except: pass
            
    nuevo = {"operador": operador, "estacion_desde": int(val_desde), "estacion_hasta": int(val_hasta), "nivel": int(nivel), "nota": nota, "correa_id": correa_id}
    try:
        supabase.table("eventos_correa").insert(nuevo).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar en Supabase: {e}")
        return False

def convertir_a_numero_puro(est_str):
    if est_str in MAPEO_LETRAS_A_NUM:
        return MAPEO_LETRAS_A_NUM[est_str]
    try: return int(est_str)
    except: return 0

def obtener_metros_reales(num_estacion, correa_id, nivel):
    factor = 1.5 if int(nivel) == 0 else (17.0 if correa_id == "CV007" else 14.0)
    if correa_id == "CV005":
        return (3823 - num_estacion) * factor
    elif correa_id == "CV006":
        return (num_estacion - (-3)) * factor
    elif correa_id == "CV007":
        return (num_estacion - 3) * factor
    return 0.0

# 4. CARGA DE IMAGEN DE FONDO
def get_base64_img(file):
    try:
        with open(file, 'rb') as f: return base64.b64encode(f.read()).decode()
    except: return None

img_tecnica_base64 = get_base64_img('correa_tecnica.png') 

# 5. TITULO PRINCIPAL DE LA APP (USANDO MÉTODO SEGURO)
st.title("📊 SISTEMA DE MONITOREO DE POLINES MEDIANTE FIBRA ÓPTICA")
st.text("High-Tech Fiber Monitoring Command Center")

tabs = st.tabs(["CV005", "CV006", "CV007"])

# ==========================================
# PESTAÑA CORREA CV005
# ==========================================
with tabs[0]:
    correa_id = "CV005"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    
    col_grafico, col_metricas = st.columns([4, 1])

    def trans_x_05(est):
        e = int(est)
        return -(e - 2000) if e >= 2000 else (2000 - e)

    total_estaciones_05 = 3823
    metros_troncal_05, metros_sensitiva_05 = 0, 0

    if not df_ev.empty:
        for _, f in df_ev.iterrows():
            cant_est = abs(int(f["estacion_desde"]) - int(f["estacion_hasta"])) + 1
            if int(f["nivel"]) == 0: metros_troncal_05 += cant_est * 1.5
            elif int(f["nivel"]) == 5: metros_sensitiva_05 += cant_est * 14.0

    porc_troncal_05 = min(((metros_troncal_05 / 1.5) / total_estaciones_05) * 100, 100.0) if total_estaciones_05 > 0 else 0
    porc_sensitiva_05 = min(((metros_sensitiva_05 / 14.0) / total_estaciones_05) * 100, 100.0) if total_estaciones_05 > 0 else 0

    with col_grafico:
        fig = go.Figure()
        
        if img_tecnica_base64:
            fig.add_layout_image(dict(
                source=f"data:image/png;base64,{img_tecnica_base64}", xref="x", yref="y", 
                x=-1823, y=-0.5, sizex=3823, sizey=2.5, 
                sizing="stretch", opacity=0.9, layer="below"
            ))

        if not df_ev.empty:
            for _, fila in df_ev.iterrows():
                try:
                    niv = int(fila["nivel"])
                    d_num, h_num = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                    xd, xh = trans_x_05(d_num), trans_x_05(h_num)
                    
                    m_desde = obtener_metros_reales(d_num, correa_id, niv)
                    m_hasta = obtener_metros_reales(h_num, correa_id, niv)
                    
                    # EFECTO NEÓN
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines", 
                        line=dict(color=DICC_NIVELES[niv]["glow"], width=15),
                        hoverinfo="skip", showlegend=False
                    ))
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines+markers", 
                        line=dict(color=DICC_NIVELES[niv]["color"], width=3), marker=dict(size=8), 
                        customdata=[[d_num, m_desde], [h_num, m_hasta]],
                        hovertemplate=(
                            f"<b>{DICC_NIVELES[niv]['nombre']}</b><br>"
                            "📍 Estación: %{customdata[0]}<br>"
                            "📏 Ubicación: %{customdata[1]:.1f} m<br><extra></extra>"
                        ),
                        showlegend=False
                    ))
                except: pass

        fig.update_layout(
            xaxis=dict(
                tickvals=[-1823, -1000, 0, 1000, 1999], 
                ticktext=["TP1 (3823)", "3000", "Centro (2000)", "1000", "EM (1)"], 
                gridcolor="rgba(0,0,0,0.02)", tickangle=0
            ), 
            yaxis=dict(range=[-3.0, 7.0], dtick=5, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), 
            plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=50, r=50, t=30, b=50), height=450
        )
        st.plotly_chart(fig, use_container_width=True, key="gr_05")

    with col_metricas:
        st.metric(label="🔴 Avance Troncal", value=f"{porc_troncal_05:.1f}%")
        st.metric(label="🟣 Avance Sensitiva", value=f"{porc_sensitiva_05:.1f}%")
        st.write("---")
        st.metric(label="M. Troncal", value=f"{metros_troncal_05:.1f} m")
        st.metric(label="M. Sensitiva", value=f"{metros_sensitiva_05:.1f} m")


# ==========================================
# PESTAÑA CORREA CV006
# ==========================================
with tabs[1]:
    correa_id = "CV006"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")

    col_grafico_06, col_metricas_06 = st.columns([4, 1])

    def trans_x_06(est_str):
        return convertir_a_numero_puro(est_str)

    total_estaciones_06 = 3526 + 3
    metros_troncal_06, metros_sensitiva_06 = 0, 0

    if not df_ev.empty:
        for _, f in df_ev.iterrows():
            cant_est = abs(convertir_a_numero_puro(str(f["estacion_desde"])) - convertir_a_numero_puro(str(f["estacion_hasta"]))) + 1
            if int(f["nivel"]) == 0: metros_troncal_06 += cant_est * 1.5
            elif int(f["nivel"]) == 5: metros_sensitiva_06 += cant_est * 14.0

    porc_troncal_06 = min(((metros_troncal_06 / 1.5) / total_estaciones_06) * 100, 100.0) if total_estaciones_06 > 0 else 0
    porc_sensitiva_06 = min(((metros_sensitiva_06 / 14.0) / total_estaciones_06) * 100, 100.0) if total_estaciones_06 > 0 else 0

    with col_grafico_06:
        fig = go.Figure()
        if img_tecnica_base64:
            fig.add_layout_image(dict(
                source=f"data:image/png;base64,{img_tecnica_base64}", xref="x", yref="y", 
                x=-3, y=-0.5, sizex=3530, sizey=2.5, sizing="stretch", opacity=0.9, layer="below"
            ))

        if not df_ev.empty:
            for _, fila in df_ev.iterrows():
                try:
                    niv = int(fila["nivel"])
                    xd, xh = trans_x_06(str(fila["estacion_desde"])), trans_x_06(str(fila["estacion_hasta"]))
                    
                    n_d = convertir_a_numero_puro(str(fila["estacion_desde"]))
                    n_h = convertir_a_numero_puro(str(fila["estacion_hasta"]))
                    m_desde = obtener_metros_reales(n_d, correa_id, niv)
                    m_hasta = obtener_metros_reales(n_h, correa_id, niv)
                    
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines", 
                        line=dict(color=DICC_NIVELES[niv]["glow"], width=15),
                        hoverinfo="skip", showlegend=False
                    ))
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines+markers", 
                        line=dict(color=DICC_NIVELES[niv]["color"], width=3), marker=dict(size=8), 
                        customdata=[[fila['estacion_desde'], m_desde], [fila['estacion_hasta'], m_hasta]],
                        hovertemplate=(
                            f"<b>{DICC_NIVELES[niv]['nombre']}</b><br>"
                            "📍 Estación: %{customdata[0]}<br>"
                            "📏 Ubicación: %{customdata[1]:.1f} m<br><extra></extra>"
                        ),
                        showlegend=False
                    ))
                except: pass

        fig.update_layout(
            xaxis=dict(
                tickvals=[-3, 1845, 1846, 3526], 
                ticktext=["3B Carga", "Centro (1845)", "Centro (1846)", "TP2 (3526)"], 
                gridcolor="rgba(0,0,0,0.02)"
            ), 
            yaxis=dict(range=[-3.0, 7.0], dtick=5, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), 
            plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=50, r=50, t=30, b=50), height=450
        )
        st.plotly_chart(fig, use_container_width=True, key="gr_06")

    with col_metricas_06:
        st.metric(label="🔴 Avance Troncal", value=f"{porc_troncal_06:.1f}%")
        st.metric(label="🟣 Avance Sensitiva", value=f"{porc_sensitiva_06:.1f}%")
        st.write("---")
        st.metric(label="M. Troncal", value=f"{metros_troncal_06:.1f} m")
        st.metric(label="M. Sensitiva", value=f"{metros_sensitiva_06:.1f} m")


# ==========================================
# PESTAÑA CORREA CV007
# ==========================================
with tabs[2]:
    correa_id = "CV007"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")

    col_grafico_07, col_metricas_07 = st.columns([4, 1])

    total_estaciones_07 = 842 - 3 + 1
    metros_troncal_07, metros_sensitiva_07 = 0, 0

    if not df_ev.empty:
        for _, f in df_ev.iterrows():
            cant_est = abs(int(f["estacion_desde"]) - int(f["estacion_hasta"])) + 1
            if int(f["nivel"]) == 0: metros_troncal_07 += cant_est * 1.5
            elif int(f["nivel"]) == 5: metros_sensitiva_07 += cant_est * 17.0

    porc_troncal_07 = min(((metros_troncal_07 / 1.5) / total_estaciones_07) * 100, 100.0) if total_estaciones_07 > 0 else 0
    porc_sensitiva_07 = min(((metros_sensitiva_07 / 17.0) / total_estaciones_07) * 100, 100.0) if total_estaciones_07 > 0 else 0

    with col_grafico_07:
        fig = go.Figure()
        if img_tecnica_base64:
            fig.add_layout_image(dict(
                source=f"data:image/png;base64,{img_tecnica_base64}", xref="x", yref="y", 
                x=3, y=-0.5, sizex=839 * 2, sizey=2.5, sizing="stretch", opacity=0.9, layer="below"
            ))

        if not df_ev.empty:
            for _, fila in df_ev.iterrows():
                try:
                    niv = int(fila["nivel"])
                    xd, xh = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                    
                    m_desde = obtener_metros_reales(xd, correa_id, niv)
                    m_hasta = obtener_metros_reales(xh, correa_id, niv)
                    
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines", 
                        line=dict(color=DICC_NIVELES[niv]["glow"], width=15),
                        hoverinfo="skip", showlegend=False
                    ))
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines+markers", 
                        line=dict(color=DICC_NIVELES[niv]["color"], width=3), marker=dict(size=8), 
                        customdata=[[xd, m_desde], [xh, m_hasta]],
                        hovertemplate=(
                            f"<b>{DICC_NIVELES[niv]['nombre']}</b><br>"
                            "📍 Estación: %{customdata[0]}<br>"
                            "📏 Ubicación: %{customdata[1]:.1f} m<br><extra></extra>"
                        ),
                        showlegend=False
                    ))
                except: pass

        fig.update_layout(
            xaxis=dict(
                range=[0, 850], 
                tickvals=[3, 200, 400, 600, 842], 
                ticktext=["TP2 (Est. 3)", "200", "400", "600", "Shuttler"], 
                gridcolor="rgba(0,0,0,0.02)"
            ), 
            yaxis=dict(range=[-3.0, 7.0], dtick=5, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), 
            plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=50, r=50, t=30, b=50), height=450
        )
        st.plotly_chart(fig, use_container_width=True, key="gr_07")

    with col_metricas_07:
        st.metric(label="🔴 Avance Troncal", value=f"{porc_troncal_07:.1f}%")
        st.metric(label="🟣 Avance Sensitiva", value=f"{porc_sensitiva_07:.1f}%")
        st.write("---")
        st.metric(label="M. Troncal", value=f"{metros_troncal_07:.1f} m")
        st.metric(label="M. Sensitiva", value=f"{metros_sensitiva_07:.1f} m")

# ==========================================
# FORMULARIOS UNIFICADOS EN EL LATERAL
# ==========================================
st.sidebar.title("📥 Panel de Control de Carga")

with st.sidebar.expander("Registrar CV005"):
    with st.form(key="f_05"):
        op = st.text_input("Operador:", key="op05")
        niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv05")
        frente = st.radio("Frente:", ["TP1 hacia Centro (Norte)", "EM hacia Centro (Sur)"], key="frente05")
        d = st.number_input("Desde:", 1, 3823, 2000, key="d05")
        h = st.number_input("Hasta:", 1, 3823, 2000, key="h05")
        nota = st.text_input("Nota:", key="nota05")
        if st.form_submit_button("Guardar CV005") and op:
            if guardar_registro(op, d, h, niv, nota, "CV005"): st.rerun()

with st.sidebar.expander("Registrar CV006"):
    with st.form(key="f_06"):
        op = st.text_input("Operador:", key="op06")
        niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv06")
        d = st.text_input("Desde (Ej: 3B Carga o número):", "1", key="d06")
        h = st.text_input("Hasta:", "1845", key="h06")
        nota = st.text_input("Nota:", key="nota06")
        if st.form_submit_button("Guardar CV006") and op:
            if guardar_registro(op, d, h, niv, nota, "CV006"): st.rerun()

with st.sidebar.expander("Registrar CV007"):
    with st.form(key="f_07"):
        op = st.text_input("Operador:", key="op07")
        niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv07")
        d = st.number_input("Desde:", 3, 842, 3, key="d07")
        h = st.number_input("Hasta:", 3, 842, 842, key="h07")
        nota = st.text_input("Nota:", key="nota07")
        if st.form_submit_button("Guardar CV007") and op:
            if guardar_registro(op, d, h, niv, nota, "CV007"): st.rerun()
