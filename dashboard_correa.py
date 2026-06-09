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

# Mapeo bidireccional definitivo para la base de datos de tipo Integer
MAPEO_LETRAS_A_NUM = {"3B Carga": -3, "2B Carga": -2, "1B Carga": -1}
MAPEO_NUM_A_LETRAS = {-3: "3B Carga", -2: "2B Carga", -1: "1B Carga"}

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
    
    if nivel in [0, 5]:
        try:
            if correa_id == "CV006":
                if int(val_desde) <= 1845:
                    supabase.table("eventos_correa").delete()\
                        .eq("correa_id", correa_id)\
                        .eq("nivel", nivel)\
                        .lte("estacion_desde", 1845).execute()
                else:
                    supabase.table("eventos_correa").delete()\
                        .eq("correa_id", correa_id)\
                        .eq("nivel", nivel)\
                        .gt("estacion_desde", 1845).execute()
            else:
                supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).execute()
        except Exception:
            pass
            
    nuevo = {
        "operador": operador, 
        "estacion_desde": int(val_desde), 
        "estacion_hasta": int(val_hasta), 
        "nivel": int(nivel), 
        "nota": nota, 
        "correa_id": correa_id
    }
    try:
        supabase.table("eventos_correa").insert(nuevo).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar en Supabase: {e}")
        return False

def convertir_a_numero_puro(est_str):
    if est_str in MAPEO_LETRAS_A_NUM:
        return MAPEO_LETRAS_A_NUM[est_str]
    try:
        return int(est_str)
    except:
        return 0

# 4. CARGA DE IMAGEN ÚNICA
def get_base64_img(file):
    try:
        with open(file, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except: 
        return None

img_base64 = get_base64_img('correa.png')

# 5. INTERFAZ PRINCIPAL MULTI-PESTAÑA
st.title("📊 Sistema de Monitoreo de Polines Mediante Fibra Óptica")

tabs = st.tabs(["CV005", "CV006", "CV007"])

# ==========================================
# PESTAÑA CORREA CV005
# ==========================================
with tabs[0]:
    correa_id = "CV005"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    st.caption("Frente Físico: TP1 (Estación 3823) ➡️ Centro (Estación 2000) ⬅️ EM (Estación 1)")
    
    col_grafico, col_metricas = st.columns([4, 1])

    def trans_x_05(est):
        e = int(est)
        return -(e - 2000) if e >= 2000 else (2000 - e)

    total_estaciones_05 = 3823
    metros_troncal_05 = 0
    metros_sensitiva_05 = 0

    if not df_ev.empty:
        for _, f in df_ev.iterrows():
            est_d, est_h = int(f["estacion_desde"]), int(f["estacion_hasta"])
            cant_est = abs(est_d - est_h) + 1
            if int(f["nivel"]) == 0:
                metros_troncal_05 += cant_est * 1.5
            elif int(f["nivel"]) == 5:
                metros_sensitiva_05 += cant_est * 14

    porc_troncal_05 = min(((metros_troncal_05 / 1.5) / total_estaciones_05) * 100, 100.0) if total_estaciones_05 > 0 else 0
    porc_sensitiva_05 = min(((metros_sensitiva_05 / 14) / total_estaciones_05) * 100, 100.0) if total_estaciones_05 > 0 else 0

    with col_grafico:
        fig = go.Figure()
        if img_base64:
            fig.add_layout_image(dict(source=f"data:image/png;base64,{img_base64}", xref="x", yref="y", x=-1823, y=-0.7, sizex=3823, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"))

        if not df_ev.empty:
            for _, fila in df_ev.iterrows():
                try:
                    niv = int(fila["nivel"])
                    d_num, h_num = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                    xd, xh = trans_x_05(d_num), trans_x_05(h_num)
                    dist = (abs(d_num - h_num) + 1) * (1.5 if niv == 0 else (14 if niv == 5 else 1.5))
                    
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines+markers", 
                        line=dict(color=DICC_NIVELES[niv]["color"], width=5), marker=dict(size=8), 
                        hovertext=f"<b>{DICC_NIVELES[niv]['nombre']}</b><br>📍 Tramo: Est. {d_num} ➔ Est. {h_num}<br>📏 Distancia: {dist:.1f} m<br>👷 Op: {fila['operador']}<br>📝 Nota: {fila['nota']}", 
                        hoverinfo="text", showlegend=False
                    ))
                except: pass

        # Eje X con metrajes explícitos en los extremos para CV005
        fig.update_layout(
            xaxis=dict(
                tickvals=[-1823, -1000, 0, 1000, 1999], 
                ticktext=["TP1 (3823) [0.0 m]", "3000", "Centro (2000)", "1000", "EM (1) [5734.5 m]"], 
                gridcolor="rgba(0,0,0,0.1)",
                tickangle=-45,
                tickfont=dict(size=12)
            ), 
            yaxis=dict(range=[-1.5, 6.0], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), 
            margin=dict(l=50, r=50, t=30, b=100), height=550,
            hovermode="closest"
        )
        st.plotly_chart(fig, use_container_width=True, key="gr_05")

    with col_metricas:
        st.markdown("### 📊 Avance General")
        st.metric(label="🔴 Avance Troncal", value=f"{porc_troncal_05:.1f}%")
        st.metric(label="🟣 Avance Sensitiva", value=f"{porc_sensitiva_05:.1f}%")
        st.markdown("---")
        st.markdown("### 📏 Metraje")
        st.metric(label="Troncal (Nivel 0)", value=f"{metros_troncal_05:.1f} m")
        st.metric(label="Sensitiva (Nivel 5)", value=f"{metros_sensitiva_05:.1f} m")

    with st.sidebar.expander(f"📥 Registrar Datos CV005"):
        with st.form(key="f_05"):
            op = st.text_input("Operador:", key="op05")
            niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv05")
            frente = st.radio("Seleccionar Tramo / Frente:", ["TP1 hacia Centro (Norte)", "EM hacia Centro (Sur)"], key="frente05")
            
            if frente == "TP1 hacia Centro (Norte)":
                d = st.number_input("Desde Estación (Punto Lejano):", 2000, 3823, 3823, key="d05_n")
                h = st.number_input("Hasta Estación (Hacia Centro 2000):", 2000, 3823, 2000, key="h05_n")
            else:
                d = st.number_input("Desde Estación (Punto Lejano):", 1, 2000, 1, key="d05_s")
                h = st.number_input("Hasta Estación (Hacia Centro 2000):", 1, 2000, 2000, key="h05_s")
                
            nota = st.text_input("Nota:", key="nota05")
            if st.form_submit_button("Guardar Registro CV005"):
                if op:
                    if guardar_registro(op, d, h, niv, nota, correa_id):
                        st.rerun()
                else: st.error("Falta ingresar Operador.")

    st.subheader("📋 Historial de Cambios")
    if not df_ev.empty: st.dataframe(df_ev, use_container_width=True)
    else: st.caption("No hay registros guardados para la CV005.")


# ==========================================
# PESTAÑA CORREA CV006 (CENTRO UNIFICADO Y METRAJES EN EXTREMOS)
# ==========================================
with tabs[1]:
    correa_id = "CV006"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    st.caption("Frente Físico: TP1 (3B Carga ➡️ 1845) 🤝 (1846 ⬅️ 3526) TP2")

    col_grafico_06, col_metricas_06 = st.columns([4, 1])

    def trans_x_06(est_str):
        n = convertir_a_numero_puro(est_str)
        if n <= 1845:
            return n - 1845
        else:
            return 3526 - n + 1

    total_estaciones_06 = 3526 + 3
    metros_troncal_06 = 0
    metros_sensitiva_06 = 0

    if not df_ev.empty:
        for _, f in df_ev.iterrows():
            n_d = convertir_a_numero_puro(str(f["estacion_desde"]))
            n_h = convertir_a_numero_puro(str(f["estacion_hasta"]))
            cant_est = abs(n_d - n_h) + 1
            if int(f["nivel"]) == 0:
                metros_troncal_06 += cant_est * 1.5
            elif int(f["nivel"]) == 5:
                metros_sensitiva_06 += cant_est * 14

    porc_troncal_06 = min(((metros_troncal_06 / 1.5) / total_estaciones_06) * 100, 100.0) if total_estaciones_06 > 0 else 0
    porc_sensitiva_06 = min(((metros_sensitiva_06 / 14) / total_estaciones_06) * 100, 100.0) if total_estaciones_06 > 0 else 0

    with col_grafico_06:
        fig = go.Figure()
        if img_base64:
            fig.add_layout_image(dict(source=f"data:image/png;base64,{img_base64}", xref="x", yref="y", x=-1848, y=-0.7, sizex=1848 + 1681, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"))

        if not df_ev.empty:
            for _, fila in df_ev.iterrows():
                try:
                    niv = int(fila["nivel"])
                    xd, xh = trans_x_06(str(fila["estacion_desde"])), trans_x_06(str(fila["estacion_hasta"]))
                    n_d = convertir_a_numero_puro(str(fila["estacion_desde"]))
                    n_h = convertir_a_numero_puro(str(fila["estacion_hasta"]))
                    dist = (abs(n_d - n_h) + 1) * (1.5 if niv == 0 else (14 if niv == 5 else 1.5))
                    
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines+markers", 
                        line=dict(color=DICC_NIVELES[niv]["color"], width=5), marker=dict(size=8), 
                        hovertext=f"<b>{DICC_NIVELES[niv]['nombre']}</b><br>📍 Tramo: {fila['estacion_desde']} ➔ {fila['estacion_hasta']}<br>📏 Distancia: {dist:.1f} m<br>👷 Op: {fila['operador']}<br>📝 Nota: {fila['nota']}", 
                        hoverinfo="text", showlegend=False
                    ))
                except: pass

        # Corrección: Unificación del punto central '1845 | 1846' para evitar encimarse y metraje en puntas
        fig.update_layout(
            xaxis=dict(
                tickvals=[trans_x_06("3B Carga"), 0, trans_x_06("3526")], 
                ticktext=["3B Carga (TP1) [0.0 m]", "Centro (1845 | 1846)", "TP2 (3526) [5293.5 m]"], 
                gridcolor="rgba(0,0,0,0.1)",
                tickangle=-45,
                tickfont=dict(size=12)
            ), 
            yaxis=dict(range=[-1.5, 6.0], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), 
            margin=dict(l=50, r=50, t=30, b=100), height=550,
            hovermode="closest"
        )
        st.plotly_chart(fig, use_container_width=True, key="gr_06")

    with col_metricas_06:
        st.markdown("### 📊 Avance General")
        st.metric(label="🔴 Avance Troncal", value=f"{porc_troncal_06:.1f}%")
        st.metric(label="🟣 Avance Sensitiva", value=f"{porc_sensitiva_06:.1f}%")
        st.markdown("---")
        st.markdown("### 📏 Metraje")
        st.metric(label="Troncal (Nivel 0)", value=f"{metros_troncal_06:.1f} m")
        st.metric(label="Sensitiva (Nivel 5)", value=f"{metros_sensitiva_06:.1f} m")

    with st.sidebar.expander(f"📥 Registrar Datos CV006"):
        frente_06 = st.radio(
            "Seleccionar Tramo / Frente:", 
            ["TP1 hacia Centro (Norte: 3B a 1845)", "TP2 hacia Centro (Sur: 3526 a 1846)"], 
            key="frente_fuera_06"
        )
        
        if frente_06 == "TP1 hacia Centro (Norte: 3B a 1845)":
            opciones_estaciones = ["3B Carga", "2B Carga", "1B Carga"] + [str(n) for n in range(1, 1846)]
            idx_def_desde = 0
            idx_def_hasta = len(opciones_estaciones) - 1
        else:
            opciones_estaciones = [str(n) for n in range(1846, 3527)]
            idx_def_desde = len(opciones_estaciones) - 1
            idx_def_hasta = 0

        with st.form(key="f_06_historial"):
            op = st.text_input("Operador:", key="op06_hist")
            niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv06_hist")
            
            d = st.selectbox("Desde Estación (Punto Lejano):", opciones_estaciones, index=idx_def_desde, key="d06_hist")
            h = st.selectbox("Hasta Estación (Hacia Centro):", opciones_estaciones, index=idx_def_hasta, key="h06_hist")
            
            nota = st.text_input("Nota:", key="nota06_hist")
            
            if st.form_submit_button("Guardar Registro CV006"):
                if op:
                    if guardar_registro(op, d, h, niv, nota, correa_id):
                        st.rerun()
                else: 
                    st.error("Falta ingresar el nombre del Operador.")
                
    st.subheader("📋 Historial de Cambios")
    if not df_ev.empty: st.dataframe(df_ev, use_container_width=True)
    else: st.caption("No hay registros guardados para la CV006.")


# ==========================================
# PESTAÑA CORREA CV007 (MÉTRICA DE EXTREMO REPARADA)
# ==========================================
with tabs[2]:
    correa_id = "CV007"
    df_ev = leer_datos(correa_id)
    st.subheader(f"Estado Actual - {correa_id}")
    st.caption("Línea Recta Continua: TP2 (Estación 3) ➡️ Shuttler (Estación 842)")

    col_grafico_07, col_metricas_07 = st.columns([4, 1])

    total_estaciones_07 = 842 - 3 + 1
    metros_troncal_07 = 0
    metros_sensitiva_07 = 0

    if not df_ev.empty:
        for _, f in df_ev.iterrows():
            est_d, est_h = int(f["estacion_desde"]), int(f["estacion_hasta"])
            cant_est = abs(est_d - est_h) + 1
            if int(f["nivel"]) == 0:
                metros_troncal_07 += cant_est * 1.5
            elif int(f["nivel"]) == 5:
                metros_sensitiva_07 += cant_est * 17 

    porc_troncal_07 = min(((metros_troncal_07 / 1.5) / total_estaciones_07) * 100, 100.0) if total_estaciones_07 > 0 else 0
    porc_sensitiva_07 = min(((metros_sensitiva_07 / 17) / total_estaciones_07) * 100, 100.0) if total_estaciones_07 > 0 else 0

    with col_grafico_07:
        fig = go.Figure()
        if img_base64:
            fig.add_layout_image(dict(source=f"data:image/png;base64,{img_base64}", xref="x", yref="y", x=3, y=-0.7, sizex=(842 - 3) * 2, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"))

        if not df_ev.empty:
            for _, fila in df_ev.iterrows():
                try:
                    niv = int(fila["nivel"])
                    xd, xh = int(fila["estacion_desde"]), int(fila["estacion_hasta"])
                    dist = (abs(xd - xh) + 1) * (1.5 if niv == 0 else (17 if niv == 5 else 1.5))
                    
                    fig.add_trace(go.Scatter(
                        x=[xd, xh], y=[niv, niv], mode="lines+markers", 
                        line=dict(color=DICC_NIVELES[niv]["color"], width=5), marker=dict(size=8), 
                        hovertext=f"<b>{DICC_NIVELES[niv]['nombre']}</b><br>📍 Tramo: Est. {xd} ➔ Est. {xh}<br>📏 Distancia: {dist:.1f} m<br>👷 Op: {fila['operador']}<br>📝 Nota: {fila['nota']}", 
                        hoverinfo="text", showlegend=False
                    ))
                except: pass

        # Eje X con metrajes explícitos en los extremos para CV007
        fig.update_layout(
            xaxis=dict(
                range=[0, 850], 
                tickvals=[3, 200, 400, 600, 842], 
                ticktext=["TP2 (Est. 3) [0.0 m]", "200", "400", "600", "Shuttler (Est. 842) [1260.0 m]"], 
                gridcolor="rgba(0,0,0,0.1)",
                tickangle=-45,
                tickfont=dict(size=12)
            ), 
            yaxis=dict(range=[-1.5, 6.0], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]), 
            margin=dict(l=50, r=50, t=30, b=100), height=550,
            hovermode="closest"
        )
        st.plotly_chart(fig, use_container_width=True, key="gr_07")

    with col_metricas_07:
        st.markdown("### 📊 Avance General")
        st.metric(label="🔴 Avance Troncal", value=f"{porc_troncal_07:.1f}%")
        st.metric(label="🟣 Avance Sensitiva", value=f"{porc_sensitiva_07:.1f}%")
        st.markdown("---")
        st.markdown("### 📏 Metraje")
        st.metric(label="Troncal (Nivel 0)", value=f"{metros_troncal_07:.1f} m")
        st.metric(label="Sensitiva (Nivel 5)", value=f"{metros_sensitiva_07:.1f} m")

    with st.sidebar.expander(f"📥 Registrar Datos CV007"):
        with st.form(key="f_07"):
            op = st.text_input("Operador:", key="op07")
            niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key="niv07")
            
            d = st.number_input("Desde Estación (Inicio):", 3, 842, 3, key="d07_lineal")
            h = st.number_input("Hasta Estación (Fin):", 3, 842, 842, key="h07_lineal")
            
            nota = st.text_input("Nota:", key="nota07")
            if st.form_submit_button("Guardar Registro CV007"):
                if op:
                    if guardar_registro(op, d, h, niv, nota, correa_id):
                        st.rerun()
                else: st.error("Falta ingresar Operador.")
                
    st.subheader("📋 Historial de Cambios")
    if not df_ev.empty: st.dataframe(df_ev, use_container_width=True)
    else: st.caption("No hay registros guardados para la CV007.")
