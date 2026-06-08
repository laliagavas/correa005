import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
import base64

# 1. CONFIGURACIÓN DE PÁGINA
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

# Mapeo especial para las estaciones con letras de la CV006 (se mapean a números altos ficticios a la izquierda del 1)
MAPEO_LETRAS_CV006 = {"3B Carga": -3, "2B Carga": -2, "1B Carga": -1}

DICC_NIVELES = {
    0: {"nombre": "Nivel 0: Fibra Óptica Troncal", "color": "red"},
    1: {"nombre": "Nivel 1: Fibra Óptica posicionada", "color": "blue"},
    2: {"nombre": "Nivel 2: Fibra Óptica dañada", "color": "orange"},
    3: {"nombre": "Nivel 3: Clip Nuevos", "color": "yellow"},
    4: {"nombre": "Nivel 4: Fibra Óptica tejida", "color": "green"},
    5: {"nombre": "Nivel 5: Fibra Óptica Sensitiva monitoreada", "color": "purple"}
}

# 3. FUNCIONES DE BASE DE DATOS
def leer_datos(correa_id):
    try:
        response = supabase.table("eventos_correa").select("*").eq("correa_id", correa_id).execute()
        return pd.DataFrame(response.data)
    except Exception:
        return pd.DataFrame()

def guardar_registro(operador, desde, hasta, nivel, nota, correa_id):
    if nivel in [0, 5]:
        # Borrado preventivo del tramo para no sobreponer capas de fondo
        try:
            supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).execute()
        except Exception:
            pass
    
    nuevo = {
        "operador": operador, "estacion_desde": str(desde), "estacion_hasta": str(hasta),
        "nivel": nivel, "nota": nota, "correa_id": correa_id
    }
    try:
        supabase.table("eventos_correa").insert(nuevo).execute()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# 4. CARGA DE IMAGEN ÚNICA
def get_base64_img(file):
    try:
        with open(file, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except: 
        return None

img_base64 = get_base64_img('correa.png')

# 5. INTERFAZ PRINCIPAL MULTI-PESTAÑA
st.title("🚀 Sistema de Monitoreo de Polines por Fibra Óptica")

tabs = st.tabs(["CV005", "CV006", "CV007"])

# ==========================================
# PESTAÑA CORREA CV005
# ==========================================
with tabs[0]:
    correa_id = "CV005"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    st.caption("Frente Físico: TP1 (Estación 3823) ➡️ Centro (Estación 2000) ⬅️ EM (Estación 1)")
    
    def trans_x_05(est):
        e = int(est)
        return -(e - 2000) if e >= 2000 else (2000 - e)

    fig = go.Figure()
    if img_base64:
        fig.add_layout_image(dict(source=f"data:image/png;base64,{img_base64}", xref="x", yref="y", x=-1823, y=-0.7, sizex=3823, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"))

    if not df_ev.empty:
        for _, fila in df_ev.iterrows():
            try:
                niv = int(fila["nivel"])
                d_num, h_num = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                xd, xh = trans_x_05(d_num), trans_x_05(h_num)
                fig.add_trace(go.Scatter(x=[xd, xh], y=[niv, niv], mode="lines+markers+text", line=dict(color=DICC_NIVELES[niv]["color"], width=5), marker=dict(size=8), text=[f"Est. {d_num}", f"Est. {h_num}"], textposition="top center", showlegend=False))
            except: pass

    fig.update_layout(xaxis=dict(tickvals=[-1823, -1000, 0, 1000, 1999], ticktext=["TP1 (3823)", "3000", "Centro (2000)", "1000", "EM (1)"], gridcolor="rgba(0,0,0,0.1)"), yaxis=dict(range=[-2.2, 6.2], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), margin=dict(l=50, r=50, t=30, b=100), height=550)
    st.plotly_chart(fig, use_container_width=True, key="gr_05")

    with st.sidebar.expander(f"📥 Registrar Datos {correa_id}"):
        with st.form(key="f_05"):
            op = st.text_input("Operador:", key="op05")
            niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv05")
            d = st.number_input("Desde Estación:", 1, 3823, 3823, key="d05")
            h = st.number_input("Hasta Estación:", 1, 3823, 2000, key="h05")
            nota = st.text_input("Nota:", key="nota05")
            if st.form_submit_button("Guardar Registro CV005"):
                if op:
                    guardar_registro(op, d, h, niv, nota, correa_id)
                    st.rerun()
                else: st.error("Falta ingresar Operador.")
                
    st.subheader("📋 Historial de Cambios")
    if not df_ev.empty: st.dataframe(df_ev, use_container_width=True)
    else: st.caption("No hay registros guardados para la CV005.")

# ==========================================
# PESTAÑA CORREA CV006
# ==========================================
with tabs[1]:
    correa_id = "CV006"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    st.caption("Frente Físico: TP1 (3B Carga ➡️ 1) ➡️ Centro (1845) ⬅️ TP2 (3526)")

    def trans_x_06(est_str):
        if est_str in MAPEO_LETRAS_CV006:
            val_ficticio = MAPEO_LETRAS_CV006[est_str]
        else:
            val_ficticio = int(est_str)
        return -(val_ficticio - 1845) if val_ficticio >= 1845 or val_ficticio < 0 else (1845 - val_ficticio)

    fig = go.Figure()
    if img_base64:
        fig.add_layout_image(dict(source=f"data:image/png;base64,{img_base64}", xref="x", yref="y", x=-1848, y=-0.7, sizex=3526 + 1848, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"))

    if not df_ev.empty:
        for _, fila in df_ev.iterrows():
            try:
                niv = int(fila["nivel"])
                xd, xh = trans_x_06(fila["estacion_desde"]), trans_x_06(fila["estacion_hasta"])
                fig.add_trace(go.Scatter(x=[xd, xh], y=[niv, niv], mode="lines+markers+text", line=dict(color=DICC_NIVELES[niv]["color"], width=5), marker=dict(size=8), text=[f"{fila['estacion_desde']}", f"{fila['estacion_hasta']}"], textposition="top center", showlegend=False))
            except: pass

    fig.update_layout(xaxis=dict(tickvals=[trans_x_06("3B Carga"), trans_x_06("1B Carga"), trans_x_06("1"), 0, trans_x_06("3526")], ticktext=["3B Carga (TP1)", "1B Carga", "Est. 1", "Centro (1845)", "TP2 (3526)"], gridcolor="rgba(0,0,0,0.1)"), yaxis=dict(range=[-2.2, 6.2], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), margin=dict(l=50, r=50, t=30, b=100), height=550)
    st.plotly_chart(fig, use_container_width=True, key="gr_06")

    with st.sidebar.expander(f"📥 Registrar Datos {correa_id}"):
        with st.form(key="f_06"):
            op = st.text_input("Operador:", key="op06")
            niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv06")
            opciones_est = ["3B Carga", "2B Carga", "1B Carga"] + [str(n) for n in range(1, 3527)]
            d = st.selectbox("Desde Estación:", opciones_est, index=0, key="d06")
            h = st.selectbox("Hasta Estación:", opciones_est, index=3, key="h06")
            nota = st.text_input("Nota:", key="nota06")
            if st.form_submit_button("Guardar Registro CV006"):
                if op:
                    guardar_registro(op, d, h, niv, nota, correa_id)
                    st.rerun()
                else: st.error("Falta ingresar Operador.")
                
    st.subheader("📋 Historial de Cambios")
    if not df_ev.empty: st.dataframe(df_ev, use_container_width=True)
    else: st.caption("No hay registros guardados para la CV006.")

# ==========================================
# PESTAÑA CORREA CV007
# ==========================================
with tabs[2]:
    correa_id = "CV007"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    st.caption("Línea Recta Continua: TP2 (Estación 3) ➡️ Shuttler (Estación 842)")

    fig = go.Figure()
    if img_base64:
        fig.add_layout_image(dict(source=f"data:image/png;base64,{img_base64}", xref="x", yref="y", x=3, y=-0.7, sizex=842 - 3, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"))

    if not df_ev.empty:
        for _, fila in df_ev.iterrows():
            try:
                niv = int(fila["nivel"])
                xd, xh = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                fig.add_trace(go.Scatter(x=[xd, xh], y=[niv, niv], mode="lines+markers+text", line=dict(color=DICC_NIVELES[niv]["color"], width=5), marker=dict(size=8), text=[f"Est. {xd}", f"Est. {xh}"], textposition="top center", showlegend=False))
            except: pass

    fig.update_layout(xaxis=dict(range=[0, 850], tickvals=[3, 200, 400, 600, 842], ticktext=["TP2 (Est. 3)", "200", "400", "600", "Shuttler (Est. 842)"], gridcolor="rgba(0,0,0,0.1)"), yaxis=dict(range=[-2.2, 6.2], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), margin=dict(l=50, r=50, t=30, b=100), height=550)
    st.plotly_chart(fig, use_container_width=True, key="gr_07")

    with st.sidebar.expander(f"📥 Registrar Datos {correa_id}"):
        with st.form(key="f_07"):
            op = st.text_input("Operador:", key="op07")
            niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv07")
            d = st.number_input("Desde Estación:", 3, 842, 3, key="d07")
            h = st.number_input("Hasta Estación:", 3, 842, 842, key="h07")
            nota = st.text_input("Nota:", key="nota07")
            if st.form_submit_button("Guardar Registro CV007"):
                if op:
                    guardar_registro(op, d, h, niv, nota, correa_id)
                    st.rerun()
                else: st.error("Falta ingresar Operador.")
                
    st.subheader("📋 Historial de Cambios")
    if not df_ev.empty: st.dataframe(df_ev, use_container_width=True)
    else: st.caption("No hay registros guardados para la CV007.")
