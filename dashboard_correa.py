import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
import base64

# Configuración de página en modo ancho
st.set_page_config(layout="wide", page_title="Sistema de Monitoreo Global - CV")

# --- CONEXIÓN A SUPABASE ---
SUPABASE_URL = "https://aumkuyciwmeevnwtsvpy.supabase.co"
SUPABASE_KEY = "sb_publishable_5Iq0mHkNsetilyAFFQo1tw_-dth1liU"

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_supabase()
except Exception:
    st.error("Error de conexión con la base de datos Supabase.")

# --- CONFIGURACIÓN DE CORREAS (METADATOS) ---
# Si en el futuro agregas la CV006, solo cambias los números de sus estaciones aquí
CONFIG_CORREAS = {
    "CV005": {"inicio": 3823, "centro": 2000, "fin": 1},
    "CV006": {"inicio": 3823, "centro": 2000, "fin": 1}, # Ajustar si cambian los límites físicos
}

# --- FUNCIONES DE BASE DE DATOS ---
def leer_datos(correa_id):
    """Lee registros filtrados por la correa seleccionada"""
    response = supabase.table("eventos_correa").select("*").eq("correa_id", correa_id).execute()
    return pd.DataFrame(response.data)

def guardar_registro(operador, desde, hasta, nivel, nota, es_frente_norte, correa_id):
    """Guarda registro con ID de correa y aplica lógica de borrado independiente"""
    centro = CONFIG_CORREAS[correa_id]["centro"]
    
    if nivel in [0, 5]:
        if es_frente_norte:
            supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).gte("estacion_desde", centro).execute()
        else:
            supabase.table("eventos_correa").delete().eq("correa_id", correa_id).eq("nivel", nivel).lte("estacion_desde", centro).execute()
    
    nuevo = {
        "operador": operador, "estacion_desde": desde, "estacion_hasta": hasta,
        "nivel": nivel, "nota": nota, "correa_id": correa_id
    }
    supabase.table("eventos_correa").insert(nuevo).execute()

def calcular_metraje(desde, hasta, nivel):
    """Calcula el metraje real según la naturaleza de la instalación"""
    estaciones_afectadas = abs(desde - hasta) + 1
    if nivel == 0:
        return estaciones_afectadas * 1.5
    elif nivel == 5:
        return estaciones_afectadas * 12
    else:
        return estaciones_afectadas * 1.5

# --- INTERFAZ PRINCIPAL ---
st.title("🚀 Central de Monitoreo de Convergencia")

DICC_NIVELES = {
    0: {"nombre": "Nivel 0: Fibra Óptica Troncal", "color": "red"},
    1: {"nombre": "Nivel 1: Fibra Óptica posicionada", "color": "blue"},
    2: {"nombre": "Nivel 2: Fibra Óptica dañada", "color": "orange"},
    3: {"nombre": "Nivel 3: Clip Nuevos", "color": "yellow"},
    4: {"nombre": "Nivel 4: Fibra Óptica tejida", "color": "green"},
    5: {"nombre": "Nivel 5: Fibra Óptica Sensitiva monitoreada", "color": "purple"}
}

# Cargar la imagen única una sola vez en memoria para optimizar rendimiento
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

try:
    encoded_image = get_base64_of_bin_file('correa.png')
    imagen_disponible = True
except FileNotFoundError:
    imagen_disponible = False

# SELECTOR DE CORREA MEDIANTE PESTAÑAS SUPERIORES
tabs_correas = st.tabs(list(CONFIG_CORREAS.keys()))

for i, correa_id in enumerate(CONFIG_CORREAS.keys()):
    with tabs_correas[i]:
        conf = CONFIG_CORREAS[correa_id]
        df_eventos = leer_datos(correa_id)
        
        st.subheader(f"Dashboard Correa {correa_id}")
        st.caption(f"Frente Operacional: TP1 ({conf['inicio']}) ➡️ {conf['centro']} ⬅️ EM ({conf['fin']})")

        # --- PROCESAMIENTO DE DATOS PARA LÓGICA CONVERGENTE ---
        def transformar_coordenada(estacion):
            if estacion >= conf['centro']:
                return -(estacion - conf['centro'])
            else:
                return (conf['centro'] - estacion)

        # --- CÁLCULO DE PORCENTAJES EN TIEMPO REAL ---
        total_estaciones_global = (conf['inicio'] - conf['centro']) + (conf['centro'] - conf['fin'])
        
        estaciones_troncal = 0
        estaciones_monit = 0

        if not df_eventos.empty:
            df_t = df_eventos[df_eventos["nivel"] == 0]
            for _, fila in df_t.iterrows():
                estaciones_troncal += abs(fila["estacion_desde"] - fila["estacion_hasta"]) + 1

            df_m = df_eventos[df_eventos["nivel"] == 5]
            for _, fila in df_m.iterrows():
                estaciones_monit += abs(fila["estacion_desde"] - fila["estacion_hasta"]) + 1

        porcentaje_troncal = min((estaciones_troncal / total_estaciones_global) * 100, 100.0) if total_estaciones_global > 0 else 0
        porcentaje_monit = min((estaciones_monit / total_estaciones_global) * 100, 100.0) if total_estaciones_global > 0 else 0

        # --- RENDERIZADO DEL GRÁFICO ---
        fig = go.Figure()

        # Insertar la imagen de fondo única
        if imagen_disponible:
            fig.add_layout_image(
                dict(
                    source=f"data:image/png;base64,{encoded_image}",
                    xref="x", yref="y",
                    x=-1850,           
                    y=-0.7,            
                    sizex=3850,        
                    sizey=1.0,         
                    sizing="stretch",
                    opacity=0.9,       
                    layer="below"
                )
            )
        else:
            st.warning("Falta el archivo 'correa.png' en GitHub para renderizar la base física.")

        # Dibujar líneas de estado con textos desfasados (Sin encimar)
        if not df_eventos.empty:
            for index, fila in df_eventos.iterrows():
                nivel_idx = int(fila["nivel"])
                n_info = DICC_NIVELES[nivel_idx]
                
                st_desde = fila["estacion_desde"]
                st_hasta = fila["estacion_hasta"]
                
                x_coord_desde = transformar_coordenada(st_desde)
                x_coord_hasta = transformar_coordenada(st_hasta)
                
                if st_desde >= conf['centro']:
                    m_desde = abs(conf['inicio'] - st_desde) * 1.5 if nivel_idx != 5 else abs(conf['inicio'] - st_desde) * 12
                    m_hasta = abs(conf['inicio'] - st_hasta) * 1.5 if nivel_idx != 5 else abs(conf['inicio'] - st_hasta) * 12
                    frente_origen = "Norte (TP1 ➡️)"
                else:
                    m_desde = abs(st_desde - conf['fin']) * 1.5 if nivel_idx != 5 else abs(st_desde - conf['fin']) * 12
                    m_hasta = abs(st_hasta - conf['fin']) * 1.5 if nivel_idx != 5 else abs(st_hasta - conf['fin']) * 12
                    frente_origen = "Sur (EM ➡️)"
                    
                metros_tramo = calcular_metraje(st_desde, st_hasta, nivel_idx)
                
                texto_desde = f"Est. {st_desde}<br>{m_desde:.0f} m"
                texto_hasta = f"Est. {st_hasta}<br>{m_hasta:.0f} m"
                
                fig.add_trace(go.Scatter(
                    x=[x_coord_desde, x_coord_hasta],
                    y=[nivel_idx, nivel_idx],
                    mode="lines+markers+text",
                    line=dict(color=n_info["color"], width=5),
                    marker=dict(color=n_info["color"], size=9),
                    text=[texto_desde, texto_hasta],
                    textposition=["top center", "bottom center"], 
                    textfont=dict(size=9, color="#555555", family="Arial"),
                    hoverinfo="text",
                    hovertext=f"Sentido: {frente_origen} Centro<br>Tramo Real: Est. {st_desde} a Est. {st_hasta}<br>Condición: {n_info['nombre']}<br>Largo del Tramo: {metros_tramo:.1f} m<br>Op: {fila['operador']}",
                    showlegend=False 
                ))

        # Configuración de Ejes Estándar
        MAX_COORD_T = -(conf['inicio'] - conf['centro'])
        MAX_COORD_E = (conf['centro'] - conf['fin'])

        tick_vals = [
            MAX_COORD_T, 
            transformar_coordenada(3600), transformar_coordenada(3200), 
            transformar_coordenada(2800), transformar_coordenada(2400),
            transformar_coordenada(2000),
            transformar_coordenada(1600), transformar_coordenada(1200),
            transformar_coordenada(800),  transformar_coordenada(400), 
            MAX_COORD_E
        ]
        tick_text = [f"TP1<br>({conf['inicio']})", '3600', '3200', '2800', '2400', f"<b>Centro</b><br>({conf['centro']})", '1600', '1200', '800', '400', f"EM<br>({conf['fin']})"]

        for niv, info in DICC_NIVELES.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=info["color"], size=10), name=info["nombre"]))

        texto_porcentajes = (
            f"<b>📊 AVANCE GENERAL</b><br>"
            f"🔴 F.O. Troncal: <b>{porcentaje_troncal:.1f}%</b><br>"
            f"🟣 F.O. Sensitiva: <b>{porcentaje_monit:.1f}%</b>"
        )

        fig.update_layout(
            xaxis=dict(title="Lógica de Convergencia Física hacia Estación Central", tickvals=tick_vals, ticktext=tick_text, tickmode='array', gridcolor="rgba(220, 220, 220, 0.3)", tickangle=-45),
            yaxis=dict(title="Capas de Inspección e Infraestructura", range=[-2.2, 6.2], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[info["nombre"] for info in DICC_NIVELES.values()], gridcolor="rgba(220, 220, 220, 0.3)"),
            margin=dict(l=50, r=360, t=30, b=120), height=720, hovermode="closest", autosize=True,
            legend=dict(yanchor="top", y=1.0, xanchor="left", x=1.04),
            annotations=[dict(xref="paper", yref="paper", x=1.04, y=0.25, xanchor="left", showarrow=False, text=texto_porcentajes, align="left", bgcolor="rgba(255, 255, 255, 0.95)", bordercolor="rgba(200, 200, 200, 0.8)", borderwidth=1, borderpad=12, font=dict(size=12, color="#333333"))]
        )
        
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{correa_id}")

        # --- FORMULARIO LATERAL DINÁMICO (Por Correa) ---
        st.sidebar.markdown(f"### 📥 Ingreso Datos {correa_id}")
        with st.sidebar.expander(f"Abrir Formulario {correa_id}", expanded=False):
            with st.form(key=f"form_{correa_id}"):
                operador = st.text_input("Operador / Mantenedor:", key=f"op_{correa_id}")
                frente_seleccionado = st.radio("Seleccione frente:", ["TP1 hacia Centro", "EM hacia Centro"], key=f"frente_{correa_id}")
                nivel_seleccionado = st.selectbox("Seleccionar Nivel:", options=list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key=f"niv_{correa_id}")
                comentario = st.text_input("Notas:", key=f"nota_{correa_id}")

                if frente_seleccionado == "TP1 hacia Centro":
                    est_desde = st.number_input("Estación Origen:", min_value=conf['centro'], max_value=conf['inicio'], value=conf['inicio'], key=f"d_{correa_id}")
                    est_hasta = st.number_input("Estación Destino:", min_value=conf['centro'], max_value=conf['inicio'], value=conf['centro'], key=f"h_{correa_id}")
                else:
                    est_desde = st.number_input("Estación Origen:", min_value=conf['fin'], max_value=conf['centro'], value=conf['fin'], key=f"d2_{correa_id}")
                    est_hasta = st.number_input("Estación Destino:", min_value=conf['fin'], max_value=conf['centro'], value=conf['centro'], key=f"h2_{correa_id}")

                if st.form_submit_button("Guardar Registro"):
                    if operador:
                        guardar_registro(operador, est_desde, est_hasta, nivel_seleccionado, comentario, frente_seleccionado == "TP1 hacia Centro", correa_id)
                        st.success(f"Datos de {correa_id} guardados.")
                        st.rerun()
                    else:
                        st.error("Ingrese el operador.")

        # --- PANEL DE METRAJES GLOBALES DE LA PESTAÑA ---
        st.markdown("### 📏 Metraje Actual")
        if not df_eventos.empty:
            col_troncal, col_monit = st.columns(2)
            df_t = df_eventos[df_eventos["nivel"] == 0]
            df_m = df_eventos[df_eventos["nivel"] == 5]
            
            with col_troncal:
                if not df_t.empty:
                    total_metros_t = sum(calcular_metraje(f["estacion_desde"], f["estacion_hasta"], 0) for _, f in df_t.iterrows())
                    st.metric(label="Fibra Óptica Troncal Instalada", value=f"{total_metros_t:.2f} metros")
                else:
                    st.metric(label="Fibra Óptica Troncal Instalada", value="0.00 metros")
                    
            with col_monit:
                if not df_m.empty:
                    total_metros_m = sum(calcular_metraje(f["estacion_desde"], f["estacion_hasta"], 5) for _, f in df_m.iterrows())
                    st.metric(label="Fibra Óptica Monitoreada", value=f"{total_metros_m:.2f} metros")
                else:
                    st.metric(label="Fibra Óptica Monitoreada", value="0.00 metros")

        # Historial de auditoría
        st.subheader("📋 Historial de Cambios")
        if not df_eventos.empty:
            st.dataframe(df_eventos.sort_values(by="created_at", ascending=False), use_container_width=True)
        else:
            st.caption("No hay registros aún para esta correa.")
