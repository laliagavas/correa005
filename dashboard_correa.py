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

# 3. CONFIGURACIÓN FÍSICA REAL DE LAS CORREAS
CONFIG_CORREAS = {
    "CV005": {"inicio": 3823, "centro": 2000, "fin": 1, "lbl_inicio": "TP1", "lbl_fin": "EM"},
    "CV006": {"inicio": 3823, "centro": 2000, "fin": 1, "lbl_inicio": "TP1", "lbl_fin": "TP2"},
    "CV007": {"inicio": 1200, "centro": 600, "fin": 1, "lbl_inicio": "TP2", "lbl_fin": "Shuttle"},
}

DICC_NIVELES = {
    0: {"nombre": "Nivel 0: Fibra Óptica Troncal", "color": "red"},
    1: {"nombre": "Nivel 1: Fibra Óptica posicionada", "color": "blue"},
    2: {"nombre": "Nivel 2: Fibra Óptica dañada", "color": "orange"},
    3: {"nombre": "Nivel 3: Clip Nuevos", "color": "yellow"},
    4: {"nombre": "Nivel 4: Fibra Óptica tejida", "color": "green"},
    5: {"nombre": "Nivel 5: Fibra Óptica Sensitiva monitoreada", "color": "purple"}
}

# 4. FUNCIONES DE BASE DE DATOS
def leer_datos(correa_id):
    """Filtra datos por el ID de la correa seleccionada"""
    response = supabase.table("eventos_correa").select("*").eq("correa_id", correa_id).execute()
    return pd.DataFrame(response.data)

def guardar_registro(operador, desde, hasta, nivel, nota, es_frente_norte, correa_id):
    """Guarda registro y limpia Nivel 0/5 solo de la correa y frente actual"""
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

# 5. CARGA DE IMAGEN ÚNICA
def get_base64_img(file):
    try:
        with open(file, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except: return None

img_base64 = get_base64_img('correa.png')

# 6. INTERFAZ MULTI-PESTAÑA
st.title("📊 Central de Monitoreo de Convergencia")

tabs = st.tabs(list(CONFIG_CORREAS.keys()))

for i, correa_id in enumerate(CONFIG_CORREAS.keys()):
    with tabs[i]:
        conf = CONFIG_CORREAS[correa_id]
        df_eventos = leer_datos(correa_id)
        
        st.subheader(f"Estado Actual - {correa_id}")
        st.caption(f"Configuración Física: {conf['lbl_inicio']} ({conf['inicio']}) ➡️ Centro ({conf['centro']}) ⬅ {conf['lbl_fin']} ({conf['fin']})")
        
        # Lógica de coordenadas según el centro de esta correa
        def trans_x(est):
            return -(est - conf['centro']) if est >= conf['centro'] else (conf['centro'] - est)

        # Cálculo de escala para el gráfico
        x_min, x_max = trans_x(conf['inicio']), trans_x(conf['fin'])
        ancho_total = abs(x_max - x_min)

        fig = go.Figure()

        # Fondo dinámico: Se ajusta al tamaño de la correa automáticamente
        if img_base64:
            fig.add_layout_image(dict(
                source=f"data:image/png;base64,{img_base64}",
                xref="x", yref="y", x=x_min - (ancho_total*0.02), y=-0.7,
                sizex=ancho_total * 1.04, sizey=1.0, sizing="stretch", opacity=0.9, layer="below"
            ))

        # Trazado de líneas y etiquetas
        if not df_eventos.empty:
            for _, fila in df_eventos.iterrows():
                niv = int(fila["nivel"])
                xd, xh = trans_x(fila["estacion_desde"]), trans_x(fila["estacion_hasta"])
                
                # Metrajes dinámicos relativos a sus frentes reales
                if fila["estacion_desde"] >= conf['centro']:
                    md = abs(conf['inicio'] - fila["estacion_desde"]) * (1.5 if niv != 5 else 12)
                    mh = abs(conf['inicio'] - fila["estacion_hasta"]) * (1.5 if niv != 5 else 12)
                    frente = f"{conf['lbl_inicio']} hacia Centro"
                else:
                    md = abs(fila["estacion_desde"] - conf['fin']) * (1.5 if niv != 5 else 12)
                    mh = abs(fila["estacion_hasta"] - conf['fin']) * (1.5 if niv != 5 else 12)
                    frente = f"{conf['lbl_fin']} hacia Centro"

                fig.add_trace(go.Scatter(
                    x=[xd, xh], y=[niv, niv], mode="lines+markers+text",
                    line=dict(color=DICC_NIVELES[niv]["color"], width=5),
                    text=[f"Est. {fila['estacion_desde']}<br>{md:.0f} m", f"Est. {fila['estacion_hasta']}<br>{mh:.0f} m"],
                    textposition=["top center", "bottom center"], textfont=dict(size=9, color="#444"),
                    hovertext=f"Op: {fila['operador']}<br>Tramo: {abs(mh-md):.1f}m", hoverinfo="text", showlegend=False
                ))

        # Configuración de Ejes Dinámicos
        paso = ancho_total / 8
        ticks_x = [x_min + (paso * j) for j in range(9)]
        labels_x = [str(int(conf['centro'] - val)) if val <=0 else str(int(conf['centro'] - val)) for val in ticks_x]
        
        # Sobrescribir extremos con los nombres reales de los terminales de esta correa
        labels_x[0] = f"{conf['lbl_inicio']}<br>({conf['inicio']})"
        labels_x[-1] = f"{conf['lbl_fin']}<br>({conf['fin']})"
        labels_x[4] = f"<b>Centro</b><br>({conf['centro']})"

        for niv, info in DICC_NIVELES.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=info["color"], size=10), name=info["nombre"]))

        fig.update_layout(
            xaxis=dict(tickvals=ticks_x, ticktext=labels_x, gridcolor="rgba(0,0,0,0.1)", tickangle=-45),
            yaxis=dict(range=[-2.2, 6.2], dtick=1, tickvals=list(DICC_NIVELES.keys()), ticktext=[n["nombre"] for n in DICC_NIVELES.values()]),
            margin=dict(l=50, r=320, t=30, b=100), height=650,
            legend=dict(y=1, x=1.05),
            annotations=[dict(xref="paper", yref="paper", x=1.05, y=0.3, showarrow=False, align="left",
                             text=f"<b>📊 ACTIVO: {correa_id}</b>", bgcolor="white", bordercolor="gray", borderwidth=1, borderpad=10)]
        )
        st.plotly_chart(fig, use_container_width=True, key=f"gr_{correa_id}")

        # Formulario Lateral
        st.sidebar.markdown(f"---")
        with st.sidebar.expander(f"📥 Registrar {correa_id}"):
            with st.form(key=f"form_{correa_id}"):
                op = st.text_input("Operador:", key=f"op_{correa_id}")
                frente = st.radio("Frente de Avance:", [f"{conf['lbl_inicio']} hacia Centro", f"{conf['lbl_fin']} hacia Centro"], key=f"fr_{correa_id}")
                niv = st.selectbox("Nivel / Condición:", list(DICC_NIVELES.keys()), format_func=lambda x: DICC_NIVELES[x]["nombre"], key=f"nv_{correa_id}")
                nota = st.text_input("Nota:", key=f"nota_{correa_id}")
                
                if frente == f"{conf['lbl_inicio']} hacia Centro":
                    d = st.number_input("Desde (Pto Lejano):", conf['centro'], conf['inicio'], conf['inicio'], key=f"d_{correa_id}")
                    h = st.number_input("Hasta (Hacia Centro):", conf['centro'], conf['inicio'], conf['centro'], key=f"h_{correa_id}")
                else:
                    d = st.number_input("Desde (Pto Lejano):", conf['fin'], conf['centro'], conf['fin'], key=f"d2_{correa_id}")
                    h = st.number_input("Hasta (Hacia Centro):", conf['fin'], conf['centro'], conf['centro'], key=f"h2_{correa_id}")
                
                if st.form_submit_button("Guardar Registro"):
                    if op:
                        guardar_registro(op, d, h, niv, nota, frente==f"{conf['lbl_inicio']} hacia Centro", correa_id)
                        st.rerun()
                    else:
                        st.error("Por favor, ingrese el nombre del operador.")

        # Historial de Auditoría protegido contra tablas vacías
        st.subheader("📋 Historial de Cambios")
        if not df_eventos.empty:
            st.dataframe(df_eventos.sort_values("created_at", ascending=False), use_container_width=True)
        else:
            st.caption("No hay registros almacenados para esta correa aún. Use el formulario lateral para ingresar el primero.")
