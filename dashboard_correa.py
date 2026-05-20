import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
import base64

# Configuración de página en modo ancho
st.set_page_config(layout="wide", page_title="Monitoreo Convergente CV005")

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

# --- FUNCIONES DE BASE DE DATOS ---
def leer_datos():
    """Lee todos los registros de la base de datos"""
    response = supabase.table("eventos_correa").select("*").execute()
    return pd.DataFrame(response.data)

def guardar_registro(operador, desde, hasta, nivel, nota, es_frente_norte):
    """
    Guarda un registro. Si es Nivel 0 o 5, borra el anterior del MISMO FRENTE
    utilizando filtros cruzados estrictos para asegurar independencia absoluta.
    """
    if nivel in [0, 5]:
        if es_frente_norte:
            supabase.table("eventos_correa")\
                .delete()\
                .eq("nivel", nivel)\
                .gte("estacion_desde", 2000)\
                .gte("estacion_hasta", 2000)\
                .execute()
        else:
            supabase.table("eventos_correa")\
                .delete()\
                .eq("nivel", nivel)\
                .lte("estacion_desde", 2000)\
                .lte("estacion_hasta", 2000)\
                .execute()
    
    nuevo = {
        "operador": operador,
        "estacion_desde": desde,
        "estacion_hasta": hasta,
        "nivel": nivel,
        "nota": nota
    }
    supabase.table("eventos_correa").insert(nuevo).execute()

# --- CÁLCULO DE METRAJE PERSONALIZADO ---
def calcular_metraje(desde, hasta, nivel):
    """Calcula el metraje real según la naturaleza de la instalación"""
    estaciones_afectadas = abs(desde - hasta) + 1
    if nivel == 0:
        return estaciones_afectadas * 1.5
    elif nivel == 5:
        return estaciones_afectadas * 12
    else:
        return estaciones_afectadas * 1.5

# --- INTERFAZ DEL DASHBOARD ---
st.title("📊 Sistema de Monitoreo de Convergencia Central - CV005")
st.markdown("### TP1 (3823) ➡️ 2000 ⬅️ EM (1)")
st.write("Datos en tiempo real TP1 y EM.")

# Cargar datos actuales
df_eventos = leer_datos()

DICC_NIVELES = {
    0: {"nombre": "Nivel 0: Fibra Óptica Troncal", "color": "red"},
    1: {"nombre": "Nivel 1: Fibra Óptica posicionada", "color": "blue"},
    2: {"nombre": "Nivel 2: Fibra Óptica dañada", "color": "orange"},
    3: {"nombre": "Nivel 3: Clip Nuevos", "color": "yellow"},
    4: {"nombre": "Nivel 4: Fibra Óptica tejida", "color": "green"},
    5: {"nombre": "Nivel 5: Fibra Óptica Sensitiva monitoreada", "color": "purple"}
}

# --- FORMULARIO EN LA BARRA LATERAL ---
st.sidebar.header("📥 Registrar Avance")
operador = st.sidebar.text_input("Operador / Mantenedor:", value="")

frente_seleccionado = st.sidebar.radio(
    "Seleccione donde operó:",
    ["TP1 hacia Centro", "EM hacia Centro"]
)

es_norte = frente_seleccionado == "TP1 hacia Centro"

with st.sidebar.form(key="formulario_ingreso"):
    nivel_seleccionado = st.selectbox(
        "Seleccionar Condición / Nivel:", 
        options=list(DICC_NIVELES.keys()), 
        format_func=lambda x: DICC_NIVELES[x]["nombre"]
    )
    comentario = st.text_input("Notas y Condición:")

    if es_norte:
        st.markdown("---")
        st.caption("Dirección de avance: Bajando desde la 3823 hacia el Centro (2000)")
        est_desde = st.number_input("Estación de Origen (Pto más lejano):", min_value=2000, max_value=3823, value=3823)
        est_hasta = st.number_input("Estación de Destino (Hacia el Centro):", min_value=2000, max_value=3823, value=2000)
    else:
        st.markdown("---")
        st.caption("Dirección de avance: Subiendo desde la 1 hacia el Centro (2000)")
        est_desde = st.number_input("Estación de Origen (Pto más lejano):", min_value=1, max_value=2000, value=1)
        est_hasta = st.number_input("Estación de Destino (Hacia el Centro):", min_value=1, max_value=2000, value=2000)

    boton_enviar = st.form_submit_button("Guardar e Imprimir Registro")
    
    if boton_enviar:
        if operador:
            if es_norte and est_hasta > est_desde:
                st.error("En el Frente Norte el avance debe ir descendiendo numéricamente hacia la 2000.")
            elif not es_norte and est_hasta < est_desde:
                st.error("En el Frente Sur el avance debe ir ascendiendo numéricamente hacia la 2000.")
            else:
                guardar_registro(operador, est_desde, est_hasta, nivel_seleccionado, comentario, es_norte)
                st.success("¡Avance registrado exitosamente!")
                st.rerun()
        else:
            st.error("Debe ingresar el nombre del operador antes de continuar.")

# --- PROCESAMIENTO DE DATOS PARA LÓGICA CONVERGENTE ---
def transformar_coordenada(estacion):
    """Mapea las estaciones de manera que el Centro (2000) quede al medio"""
    CENTRO_CONVERGENCIA = 2000
    if estacion >= CENTRO_CONVERGENCIA:
        return -(estacion - CENTRO_CONVERGENCIA)
    else:
        return (CENTRO_CONVERGENCIA - estacion)

# --- CÁLCULO DE PORCENTAJES EN TIEMPO REAL ---
TOTAL_ESTACIONES_GLOBAL = 3822

estaciones_troncal = 0
estaciones_monit = 0

if not df_eventos.empty:
    df_t = df_eventos[df_eventos["nivel"] == 0]
    for _, fila in df_t.iterrows():
        estaciones_troncal += abs(fila["estacion_desde"] - fila["estacion_hasta"]) + 1

    df_m = df_eventos[df_eventos["nivel"] == 5]
    for _, fila in df_m.iterrows():
        estaciones_monit += abs(fila["estacion_desde"] - fila["estacion_hasta"]) + 1

porcentaje_troncal = min((estaciones_troncal / TOTAL_ESTACIONES_GLOBAL) * 100, 100.0)
porcentaje_monit = min((estaciones_monit / TOTAL_ESTACIONES_GLOBAL) * 100, 100.0)

# --- RENDERIZADO DEL GRÁFICO INTERACTIVO ---
fig = go.Figure()

# --- INSERTAR FOTO DE LA CORREA ABAJO (Ajustada para que no se corte) ---
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

try:
    img_path = 'correa.png' 
    encoded_image = get_base64_of_bin_file(img_path)
    fig.add_layout_image(
        dict(
            source=f"data:image/png;base64,{encoded_image}",
            xref="x", yref="y",
            x=-1850,           
            y=-0.7,            # Subimos levemente la correa dentro del plano Y
            sizex=3850,        
            sizey=1.0,         # Calibrado para evitar que la base matemática la recorte
            sizing="stretch",
            opacity=0.9,       
            layer="below"
        )
    )
except FileNotFoundError:
    st.warning("Falta el archivo 'correa.png' en el directorio para renderizar la base física.")

# --- DIBUJAR LÍNEAS DE ESTADO Y ANOTACIONES DE EXTREMO ---
if not df_eventos.empty:
    for index, fila in df_eventos.iterrows():
        nivel_idx = int(fila["nivel"])
        n_info = DICC_NIVELES[nivel_idx]
        
        st_desde = fila["estacion_desde"]
        st_hasta = fila["estacion_hasta"]
        
        x_coord_desde = transformar_coordenada(st_desde)
        x_coord_hasta = transformar_coordenada(st_hasta)
        
        if st_desde >= 2000:
            m_desde = abs(3823 - st_desde) * 1.5 if nivel_idx != 5 else abs(3823 - st_desde) * 12
            m_hasta = abs(3823 - st_hasta) * 1.5 if nivel_idx != 5 else abs(3823 - st_hasta) * 12
            frente_origen = "Norte (TP1 ➡️)"
        else:
            m_desde = abs(st_desde - 1) * 1.5 if nivel_idx != 5 else abs(st_desde - 1) * 12
            m_hasta = abs(st_hasta - 1) * 1.5 if nivel_idx != 5 else abs(st_hasta - 1) * 12
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

# --- CONFIGURACIÓN DE EJES Y DISEÑO DE CONVERGENCIA ---
CENTRO_CONVERGENCIA = 2000
MAX_COORD_T = -1823 
MAX_COORD_E = 1999  

tick_vals = [
    MAX_COORD_T, 
    transformar_coordenada(3600), 
    transformar_coordenada(3200), 
    transformar_coordenada(2800), 
    transformar_coordenada(2400),
    transformar_coordenada(2000),
    transformar_coordenada(1600),
    transformar_coordenada(1200),
    transformar_coordenada(800), 
    transformar_coordenada(400), 
    MAX_COORD_E
]
tick_text = ['TP1<br>(3823)', '3600', '3200', '2800', '2400', '<b>Centro</b><br>(2000)', '1600', '1200', '800', '400', 'EM<br>(1)']

for niv, info in DICC_NIVELES.items():
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=info["color"], size=10), name=info["nombre"]))

# --- ANOTACIONES DE AVANCE EN PORCENTAJE ---
texto_porcentajes = (
    f"<b>📊 AVANCE GENERAL</b><br>"
    f"🔴 F.O. Troncal: <b>{porcentaje_troncal:.1f}%</b><br>"
    f"🟣 F.O. Sensitiva: <b>{porcentaje_monit:.1f}%</b>"
)

fig.update_layout(
    xaxis=dict(
        title="Lógica de Convergencia Física hacia Estación Central 2000",
        tickvals=tick_vals,
        ticktext=tick_text,
        tickmode='array',
        gridcolor="rgba(220, 220, 220, 0.3)",
        tickangle=-45 
    ),
    yaxis=dict(
        title="Capas de Inspección e Infraestructura",
        range=[-2.2, 6.2], # Bajamos el rango mínimo para dar un colchón abajo a la imagen
        dtick=1,
        tickvals=list(DICC_NIVELES.keys()),
        ticktext=[info["nombre"] for info in DICC_NIVELES.values()],
        gridcolor="rgba(220, 220, 220, 0.3)"
    ),
    margin=dict(l=50, r=360, t=30, b=120), # Ampliado el margen inferior b=120
    height=720, 
    hovermode="closest",
    autosize=True,
    legend=dict(
        yanchor="top",
        y=1.0,
        xanchor="left",
        x=1.04
    ),
    annotations=[
        dict(
            xref="paper", yref="paper",
            x=1.04, y=0.25,            
            xanchor="left",            
            showarrow=False,
            text=texto_porcentajes,
            align="left",
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="rgba(200, 200, 200, 0.8)",
            borderwidth=1,
            borderpad=12,
            font=dict(size=12, color="#333333")
        )
    ]
)

st.plotly_chart(fig, use_container_width=True)

# --- PANEL DE METRAJES GLOBALES ---
st.markdown("### 📏 Metraje Actual de Fibra Óptica")
if not df_eventos.empty:
    col_troncal, col_monit = st.columns(2)
    df_t = df_eventos[df_eventos["nivel"] == 0]
    df_m = df_eventos[df_eventos["nivel"] == 5]
    
    with col_troncal:
        if not df_t.empty:
            total_metros_t = sum(calcular_metraje(f["estacion_desde"], f["estacion_hasta"], 0) for _, f in df_t.iterrows())
            st.metric(label="Fibra Óptica Troncal Instalada (Lineal)", value=f"{total_metros_t:.2f} metros", delta="Nivel 0")
        else:
            st.metric(label="Fibra Óptica Troncal Instalada (Lineal)", value="0.00 metros", delta="Sin registros")
            
    with col_monit:
        if not df_m.empty:
            total_metros_m = sum(calcular_metraje(f["estacion_desde"], f["estacion_hasta"], 5) for _, f in df_m.iterrows())
            st.metric(label="Fibra Óptica Monitoreada Instalada (Tejida)", value=f"{total_metros_m:.2f} metros", delta="Nivel 5")
        else:
            st.metric(label="Fibra Óptica Monitoreada Instalada (Tejida)", value="0.00 metros", delta="Sin registros")

# --- SECTORES DE AVANCE ---
st.markdown("### 🗺️ Frentes de Avance Operacionales")
col_norte, col_sur = st.columns(2)
with col_norte:
    st.info("**TP1**: Avance desde estación 3823 hacia el centro (estación 2000).")
with col_sur:
    st.success("**EM**: Avance desde estación 1 hacia el centro (estación 2000).")

# Tabla de auditoría
st.subheader("📋 Datos Almacenados en Supabase")
if not df_eventos.empty:
    st.dataframe(df_eventos.sort_values(by="created_at", ascending=False), use_container_width=True)
else:
    st.caption("Base de datos vacía.")