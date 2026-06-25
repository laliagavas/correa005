import math
import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# 1. CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="VMS SENSOIL",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    section[data-testid="stSidebar"] { display: none; }
    .stTabs [data-baseweb="tab-list"] { background-color: #161b22; border-radius: 8px; padding: 4px; }
    .stTabs [data-baseweb="tab"] { color: #8b949e; border-radius: 6px; }
    .stTabs [aria-selected="true"] { background-color: #1f6feb !important; color: white !important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; color: #58a6ff; }
    [data-testid="stMetricLabel"] { color: #8b949e; font-size: 0.75rem; }
    .stButton > button {
        background: linear-gradient(135deg, #1f6feb, #388bfd);
        color: white; border: none; border-radius: 8px;
        font-weight: 600; padding: 0.5rem 1.2rem;
        transition: all 0.2s ease;
    }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(31,111,235,0.4); }
    #MainMenu, header, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 2. CONFIGURACIÓN DE PROYECTOS
# ─────────────────────────────────────────────
CONFIG_PROYECTOS = {
    "DRF": {
        "nombre_estacion": "Relave A",
        "csv_data":    "DRF.csv",
        "csv_rain":    "DRFRain.csv",
        "csv_monitor": "DRFFTPMonitor.csv",
        "densidad":    1.89,
        "max_sensores": 7,
        "angle_deg":   55.0,
        "diametro_perforacion": "HQ (96 mm)",
        "tipo_instalacion": "Tubo PVC Ø 2\" Ranurado",
        "fecha_instalacion": "—",
        "soil_layers": [
            "#A0875A", "#8C7050", "#7A5C40",
            "#6B4E34", "#5C4128", "#4A3220", "#3A2318",
        ],
    },
    "ROMERAL": {
        "nombre_estacion": "Relave B",
        "csv_data":    "Romeral.csv",
        "csv_rain":    "RomeralRain.csv",
        "csv_monitor": "RomeralFTPMonitor.csv",
        "densidad":    1.75,
        "max_sensores": 8,
        "angle_deg":   55.0,
        "diametro_perforacion": "HQ (96 mm)",
        "tipo_instalacion": "Tubo PVC Ø 2\" Ranurado",
        "fecha_instalacion": "—",
        "soil_layers": [
            "#9E8B6A", "#8A7255", "#785E42", "#664A30",
            "#563D22", "#422E18", "#321F0E", "#241408",
        ],
    },
}

# ─────────────────────────────────────────────
# 3. UTILIDADES
# ─────────────────────────────────────────────
@st.cache_data
def cargar_datos_proyecto(id_proyecto: str):
    cfg = CONFIG_PROYECTOS[id_proyecto]
    try:
        df = pd.read_csv(cfg["csv_data"], skiprows=[0, 2, 3])
        df.columns = df.columns.str.replace('"', '').str.replace("'", "").str.strip()
        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'].astype(str).str.replace('"', ''))
        return df, None
    except Exception as e:
        return None, f"Error al abrir {cfg['csv_data']}: {e}"

def cargar_pluviometro_bateria(id_proyecto: str):
    cfg = CONFIG_PROYECTOS[id_proyecto]
    rain_val = "N/D"
    bat_val = "N/D"
    if os.path.exists(cfg["csv_rain"]):
        try:
            df_rain = pd.read_csv(cfg["csv_rain"], sep=",")
            if not df_rain.empty:
                val = df_rain.iloc[-1, 3]
                rain_val = f"{float(val):.2f}"
        except Exception:
            pass
    if os.path.exists(cfg["csv_monitor"]):
        try:
            df_bat = pd.read_csv(cfg["csv_monitor"], sep=",")
            if not df_bat.empty:
                val = df_bat.iloc[-1, 2]
                bat_val = f"{float(val):.2f}"
        except Exception:
            pass
    return rain_val, bat_val

def get_cols(df, prefix, n):
    cols = sorted(
        [c for c in df.columns if c.startswith(f"{prefix}_")],
        key=lambda x: int(x.split('_')[1]) if len(x.split('_')) > 1 and x.split('_')[1].isdigit() else 0
    )
    return cols[:n]

def fmt_depth(col_name: str) -> str:
    try:
        parts = col_name.split('_')
        if len(parts) >= 3:
            cm = float(parts[2].replace('cm', '').replace('CM', ''))
            return f"{cm / 100:.2f} m"
    except Exception:
        pass
    return "N/A"

def safe_val(serie, col, decimals=2):
    try:
        return f"{float(serie[col]):.{decimals}f}"
    except Exception:
        return "N/D"

def calcular_gwc(vwc_str: str, densidad: float) -> str:
    try:
        v = float(vwc_str)
        return f"{(v / densidad):.2f}"
    except Exception:
        return "N/D"

def estado_sensor(vwc_str: str) -> str:
    try:
        v = float(vwc_str)
        if v > 45 or v < 2:
            return "ALERTA"
    except Exception:
        pass
    return "NORMAL"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NUEVO COMPONENTE HTML DEL PERFIL DE SUELO
#    Reemplaza completamente la función render_soil_profile() anterior.
#    — Tooltip posicionado en capa HTML (nunca queda oculto por otro sensor)
#    — Layout responsivo (funciona en móvil)
#    — Sin altura fija: se adapta al número de sensores
# ═══════════════════════════════════════════════════════════════════════════════

def render_soil_profile(id_proyecto, cfg, cols_vwc, cols_temp, cols_pt, cols_dpt,
                        ultimo_reg, rain_val, bat_val, selected_idx=0):
    """
    Genera el HTML completo del perfil de suelo interactivo.
    Retorna un string HTML listo para usar con st.components.v1.html().
    """
    n_sens   = cfg["max_sensores"]
    densidad = cfg["densidad"]
    layers   = cfg["soil_layers"]

    # Construir lista de sensores con todos sus valores
    sensors = []
    for i in range(n_sens):
        cv = cols_vwc[i]  if i < len(cols_vwc)  else None
        ct = cols_temp[i] if i < len(cols_temp) else None
        cp = cols_pt[i]   if i < len(cols_pt)   else None
        cd = cols_dpt[i]  if i < len(cols_dpt)  else None

        vwc_v = safe_val(ultimo_reg, cv, 2) if cv else "N/D"
        sensors.append({
            "idx":   i,
            "label": f"S{i+1}",
            "depth": fmt_depth(cv) if cv else f"{(i+1)*80/100:.2f} m",
            "vwc":   vwc_v,
            "gwc":   calcular_gwc(vwc_v, densidad),
            "temp":  safe_val(ultimo_reg, ct, 1) if ct else "N/D",
            "pt":    safe_val(ultimo_reg, cp, 0) if cp else "N/D",
            "dpt":   safe_val(ultimo_reg, cd, 1) if cd else "N/D",
        })

    sensors_json  = json.dumps(sensors)
    layers_json   = json.dumps(layers)
    estado_general = estado_sensor(sensors[selected_idx]["vwc"] if sensors else "N/D")

    # Altura del iframe: escala con el número de sensores
    iframe_h = 110 + n_sens * 72 + 60    # topbar + perfil SVG

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.31.0/dist/tabler-icons.min.css">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:#0d1117;color:#e6edf3;max-width:1100px;margin:0 auto;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;overflow-x:hidden}}
.topbar{{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid #21262d;flex-wrap:wrap;gap:6px}}
.topbar-left{{display:flex;align-items:center;gap:8px}}
.logo-badge{{width:30px;height:30px;border-radius:7px;background:#1f3a5c;display:flex;align-items:center;justify-content:center;color:#58a6ff;font-size:14px}}
.topbar-title{{font-size:14px;font-weight:600;color:#e6edf3}}
.topbar-sub{{font-size:11px;color:#8b949e}}
.demo-pill{{background:#2d2205;color:#d29922;border:1px solid #4a3800;border-radius:20px;padding:3px 9px;font-size:10px;font-weight:600}}
.live-dot{{width:6px;height:6px;border-radius:50%;background:#3dd68c;display:inline-block;margin-right:4px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.main-grid{{display:grid;grid-template-columns:160px 1fr 185px;min-height:420px}}
.sidebar{{border-right:1px solid #21262d;padding:10px}}
.sidebar-label{{font-size:10px;font-weight:600;color:#8b949e;letter-spacing:.07em;text-transform:uppercase;margin-bottom:5px}}
.sensor-btn{{display:flex;align-items:center;gap:6px;width:100%;padding:5px 7px;border:1px solid #30363d;border-radius:7px;background:transparent;cursor:pointer;font-size:11px;color:#e6edf3;margin-bottom:3px;transition:background .12s}}
.sensor-btn:hover{{background:#161b22}}
.sensor-btn.active{{background:#1f3a5c;border-color:#1f6feb;color:#58a6ff}}
.sensor-dot{{width:6px;height:6px;border-radius:50%;background:#30363d;flex-shrink:0}}
.sensor-btn.active .sensor-dot{{background:#58a6ff}}
.sensor-depth{{font-size:10px;color:#8b949e;margin-left:auto}}
.sensor-btn.active .sensor-depth{{color:#58a6ff;opacity:.8}}
.sp-ok{{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:20px;font-size:10px;font-weight:600;background:#0d2a1a;color:#3dd68c;border:1px solid #1a4a2a;margin-top:6px}}
.sp-warn{{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:20px;font-size:10px;font-weight:600;background:#2d1b00;color:#d29922;border:1px solid #4a3000;margin-top:6px}}
.legend-row{{display:flex;align-items:center;gap:6px;font-size:11px;color:#8b949e;padding:3px 0;line-height:1.4}}

.profile-area{{padding:10px;display:flex;flex-direction:column;gap:6px}}
.profile-wrap{{position:relative;border-radius:10px;border:1px solid #21262d;overflow:hidden}}
.profile-svg{{display:block;width:100%}}


.det-panel{{border-left:1px solid #21262d;padding:10px;display:flex;flex-direction:column;gap:8px}}
.det-card{{background:#161b22;border:1px solid #21262d;border-radius:9px;padding:9px 11px}}
.det-title{{font-size:10px;font-weight:600;color:#8b949e;letter-spacing:.07em;text-transform:uppercase;margin-bottom:7px}}
.det-row{{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #21262d;font-size:11px}}
.det-row:last-child{{border-bottom:none}}
.det-row span:first-child{{color:#8b949e}}
.det-row span:last-child{{font-weight:600;color:#e6edf3}}
.rb-grid{{display:grid;grid-template-columns:1fr 1fr;gap:5px}}
.rb-card{{background:#161b22;border:1px solid #21262d;border-radius:9px;padding:7px 9px;text-align:center}}
.rb-label{{font-size:9px;color:#8b949e;margin-bottom:2px}}
.rb-val{{font-size:15px;font-weight:600;color:#e6edf3}}
.rb-unit{{font-size:9px;color:#8b949e}}

@media(max-width:560px){{
  .main-grid{{grid-template-columns:1fr}}
  .sidebar{{border-right:none;border-bottom:1px solid #21262d;display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start}}
  .sidebar>div{{flex:1;min-width:130px}}
  .det-panel{{border-left:none;border-top:1px solid #21262d;flex-direction:row;flex-wrap:wrap}}
  .det-card{{flex:1;min-width:140px}}
}}
</style>
</head><body>

<div class="topbar">
  <div class="topbar-left">
    <div class="logo-badge"><i class="ti ti-radar-2"></i></div>
    <div>
      <div class="topbar-title">VMS Sensoil — {cfg['nombre_estacion']}</div>
      <div class="topbar-sub">ρ {densidad} g/cm³ · Inclinación {cfg['angle_deg']:.0f}° · {n_sens} sensores activos</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <span class="demo-pill">Datos históricos</span>
    <span style="font-size:11px;color:#8b949e"><span class="live-dot"></span>Última lectura</span>
  </div>
</div>

<div class="main-grid">

  <!-- SIDEBAR IZQUIERDO -->
  <div class="sidebar">
    <div>
      <div class="sidebar-label">Sensores</div>
      <div id="sensor-list"></div>
      <div id="status-badge"></div>
    </div>
    <div style="margin-top:12px">
      <div class="sidebar-label">Referencia</div>
      <div class="legend-row"><i class="ti ti-droplet" style="font-size:12px"></i>VWC — vol.</div>
      <div class="legend-row"><i class="ti ti-plant" style="font-size:12px"></i>GWC — grav.</div>
      <div class="legend-row"><i class="ti ti-temperature" style="font-size:12px"></i>Temperatura</div>
      <div class="legend-row"><i class="ti ti-gauge" style="font-size:12px"></i>Presión poros</div>
      <div class="legend-row"><i class="ti ti-ruler" style="font-size:12px"></i>Nivel hidrost.</div>
    </div>
  </div>

  <!-- PERFIL CENTRAL -->
  <div class="profile-area">
    <div class="profile-wrap" id="profile-wrap">
      <svg id="profile-svg" class="profile-svg" viewBox="0 0 280 480" xmlns="http://www.w3.org/2000/svg"></svg>
    </div>
    <div style="font-size:10px;color:#6e7681;text-align:center">
      <i class="ti ti-hand-finger" style="font-size:11px;vertical-align:-1px;margin-right:2px"></i>
      Selecciona un sensor para ver sus datos
    </div>

  </div>

  <!-- PANEL DERECHO -->
  <div class="det-panel">
    <div class="det-card" id="detail-card">
      <div class="det-title">Lectura activa</div>
    </div>
    <div class="det-card">
      <div class="det-title">Pozo</div>
      <div class="det-row"><span>Inclinación</span><span>{cfg['angle_deg']:.0f}°</span></div>
      <div class="det-row"><span>Sensores</span><span>{n_sens}</span></div>
      <div class="det-row"><span>Diámetro</span><span>{cfg['diametro_perforacion']}</span></div>
      <div class="det-row"><span>Instalación</span><span style="font-size:10px">{cfg['tipo_instalacion']}</span></div>
    </div>
    <div class="rb-grid">
      <div class="rb-card">
        <div class="rb-label"><i class="ti ti-cloud-rain" style="font-size:10px"></i> Lluvia</div>
        <div class="rb-val">{rain_val}</div>
        <div class="rb-unit">mm</div>
      </div>
      <div class="rb-card">
        <div class="rb-label"><i class="ti ti-battery-2" style="font-size:10px"></i> Batería</div>
        <div class="rb-val">{bat_val}</div>
        <div class="rb-unit">V</div>
      </div>
    </div>
  </div>
</div>

<script>
const SENSORS  = {sensors_json};
const LAYERS   = {layers_json};
const N        = SENSORS.length;
let selIdx     = {selected_idx};

function sensorPos(i) {{
  const W=280, H=480, SY=80;
  const spacing = (H - SY - 40) / (N + 0.5);
  const dy = (i + 1) * spacing;
  const dx = dy * Math.tan(16 * Math.PI / 180);
  return {{ x: W * 0.38 + dx, y: SY + dy }};
}}

function buildSVG() {{
  const W=280, H=480, SY=80;
  const lh = (H - SY) / LAYERS.length;
  let h = `<defs><linearGradient id="skyg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#b8d8ee"/>
    <stop offset="100%" stop-color="#9ec8e4"/>
  </linearGradient></defs>`;
  h += `<rect x="0" y="0" width="${{W}}" height="${{SY}}" fill="url(#skyg)"/>`;
  LAYERS.forEach((c, i) => {{
    const y = SY + i * lh, ht = i < LAYERS.length - 1 ? lh + 1 : H - y;
    h += `<rect x="0" y="${{y}}" width="${{W}}" height="${{ht}}" fill="${{c}}"/>`;
    if (i > 0) h += `<line x1="0" y1="${{y}}" x2="${{W}}" y2="${{y}}" stroke="#2a1508" stroke-width="0.5" opacity="0.3"/>`;
  }});
  h += `<rect x="0" y="${{SY}}" width="${{W}}" height="6" fill="#9a7c48"/>`;
  h += `<rect x="100" y="20" width="70" height="46" rx="6" fill="#ddeeff" stroke="#80aacc" stroke-width="0.7"/>
        <rect x="108" y="13" width="54" height="10" rx="3" fill="#4a90d9" stroke="#2a70b9" stroke-width="0.5"/>
        <text x="135" y="41" text-anchor="middle" font-family="sans-serif" font-size="10" font-weight="600" fill="#1a3a5c">VMS</text>
        <text x="135" y="55" text-anchor="middle" font-family="sans-serif" font-size="8" fill="#3a6080">Estación</text>
        <line x1="158" y1="13" x2="164" y2="5" stroke="#4a7a9a" stroke-width="1"/>
        <circle cx="165" cy="4" r="2" fill="none" stroke="#4a9ad9" stroke-width="1"/>`;
  const last = sensorPos(N - 1);
  const cx0 = W * 0.38;
  h += `<line x1="${{cx0}}" y1="${{SY+4}}" x2="${{last.x.toFixed(1)}}" y2="${{last.y.toFixed(1)}}" stroke="#2e7a2e" stroke-width="3.5" stroke-linecap="round" opacity="0.85"/>`;
  h += `<line x1="${{cx0+3}}" y1="${{SY+4}}" x2="${{(last.x+3).toFixed(1)}}" y2="${{last.y.toFixed(1)}}" stroke="#c8a820" stroke-width="2.2" stroke-linecap="round" opacity="0.8"/>`;
  h += `<line x1="252" y1="${{SY}}" x2="252" y2="${{H-20}}" stroke="white" stroke-width="0.3" opacity="0.2"/>`;
  SENSORS.forEach((s, i) => {{
    const p = sensorPos(i);
    h += `<line x1="247" y1="${{p.y.toFixed(1)}}" x2="257" y2="${{p.y.toFixed(1)}}" stroke="#7dc3ff" stroke-width="0.5" opacity="0.45"/>`;
    h += `<text x="260" y="${{(p.y+3).toFixed(1)}}" font-family="sans-serif" font-size="7.5" fill="rgba(125,195,255,0.65)">${{s.depth}}</text>`;
  }});
  SENSORS.forEach((s, i) => {{
    const p = sensorPos(i);
    const isSel = i === selIdx;
    const ring = isSel ? '#ffe066' : '#7dc3ff';
    h += `<g class="pin" data-idx="${{i}}" style="cursor:pointer">
      <circle cx="${{p.x.toFixed(1)}}" cy="${{p.y.toFixed(1)}}" r="12" fill="#1f7fe8" opacity="0.07"/>
      <circle cx="${{p.x.toFixed(1)}}" cy="${{p.y.toFixed(1)}}" r="7.5" fill="#0e2d5c" stroke="${{ring}}" stroke-width="1.8"/>
      <circle cx="${{p.x.toFixed(1)}}" cy="${{p.y.toFixed(1)}}" r="2.8" fill="${{ring}}"/>
      <rect x="${{(p.x+9).toFixed(1)}}" y="${{(p.y-9).toFixed(1)}}" width="24" height="13" rx="3" fill="#0a1f3c" stroke="${{ring}}" stroke-width="0.6"/>
      <text x="${{(p.x+21).toFixed(1)}}" y="${{(p.y+0.5).toFixed(1)}}" text-anchor="middle" dominant-baseline="central"
            font-family="sans-serif" font-size="8" font-weight="700" fill="${{ring}}">${{s.label}}</text>
    </g>`;
  }});
  document.getElementById('profile-svg').innerHTML = h;
  document.querySelectorAll('.pin').forEach(pin => {{
    const i = parseInt(pin.dataset.idx);
    pin.addEventListener('touchstart', e => {{ e.preventDefault(); selectSensor(i); }});
    pin.addEventListener('click', () => selectSensor(i));
  }});
}}

function selectSensor(i) {{
  selIdx = i;
  buildSVG();
  buildSensorList();
  buildDetailCard();
  // Notifica a Streamlit el sensor seleccionado
  window.parent.postMessage({{
    isstreamlitMessage: true,
    type: "streamlit:setComponentValue",
    value: i
  }}, "*");
}}

function buildSensorList() {{
  document.getElementById('sensor-list').innerHTML = SENSORS.map((s, i) =>
    `<button class="sensor-btn${{i === selIdx ? ' active' : ''}}" onclick="selectSensor(${{i}})">
      <span class="sensor-dot"></span>
      <span>${{s.label}}</span>
      <span class="sensor-depth">${{s.depth}}</span>
    </button>`
  ).join('');
  const hasAlert = SENSORS.some(s => parseFloat(s.vwc) > 45 || parseFloat(s.vwc) < 2);
  document.getElementById('status-badge').innerHTML = hasAlert
    ? '<span class="sp-warn">⚠ Alerta</span>'
    : '<span class="sp-ok">✓ Normal</span>';
}}

function buildDetailCard() {{
  const s = SENSORS[selIdx];
  document.getElementById('detail-card').innerHTML = `
    <div class="det-title">Sensor ${{s.label}} · ${{s.depth}}</div>
    <div class="det-row"><span>VWC</span><span style="color:#3dd68c">${{s.vwc}} %</span></div>
    <div class="det-row"><span>GWC</span><span style="color:#3dd68c">${{s.gwc}} %</span></div>
    <div class="det-row"><span>Temperatura</span><span style="color:#f6a03a">${{s.temp}} °C</span></div>
    <div class="det-row"><span>Presión</span><span style="color:#a78bfa">${{s.pt}} mb</span></div>
    <div class="det-row"><span>Nivel</span><span style="color:#38bdf8">${{s.dpt}} cm</span></div>`;
}}

buildSVG();
buildSensorList();
buildDetailCard();

window.parent.postMessage({{
  isstreamlitMessage: true,
  type: "streamlit:setFrameHeight",
  height: document.body.scrollHeight + 20
}}, "*");
</script>
</body></html>"""


# ─────────────────────────────────────────────
# 5. MODAL HISTÓRICO (sin cambios)
# ─────────────────────────────────────────────
@st.dialog("📊 Histórico e Instrumentación del Sensor", width="large")
def modal_historico(id_proyecto, idx, df_data, cols_vwc, cols_temp, cols_pt, cols_dpt):
    cfg = CONFIG_PROYECTOS[id_proyecto]
    densidad = cfg["densidad"]

    cv = cols_vwc[idx]  if idx < len(cols_vwc)  else None
    ct = cols_temp[idx] if idx < len(cols_temp) else None
    cp = cols_pt[idx]   if idx < len(cols_pt)   else None
    cd = cols_dpt[idx]  if idx < len(cols_dpt)  else None
    prof = fmt_depth(cv) if cv else "N/A"

    st.markdown("##### ⚙️ Configuración de Consulta")
    c_fecha, c_var = st.columns(2)

    with c_fecha:
        fecha_max_global = df_data['TIMESTAMP'].max().date() if 'TIMESTAMP' in df_data.columns else pd.Timestamp.now().date()
        fecha_sel = st.date_input(
            "📅 Selecciona fecha de simulación:",
            value=fecha_max_global,
            key=f"modal_date_{id_proyecto}_{idx}"
        )

    with c_var:
        opciones_variables = [
            "Humedad (VWC %)", "Humedad Gravimétrica (GWC %)",
            "Temperatura (°C)", "Presión de Celda (mbar)", "Nivel (cm)"
        ]
        variable_grafico = st.selectbox(
            "📈 Variable para Tendencia Histórica:",
            options=opciones_variables,
            index=0,
            key=f"modal_var_{id_proyecto}_{idx}"
        )

    st.markdown("---")

    fecha_limite_kpi = pd.to_datetime(fecha_sel) + pd.Timedelta(days=1)
    df_actual = df_data[df_data['TIMESTAMP'] < fecha_limite_kpi]

    if not df_actual.empty:
        ultimo_registro = df_actual.iloc[-1]
        fecha_lectura_str = ultimo_registro['TIMESTAMP'].strftime('%Y-%m-%d %H:%M')
    else:
        ultimo_registro = df_data.iloc[-1] if not df_data.empty else None
        fecha_lectura_str = "Sin datos para esta fecha"

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1f6feb22,#388bfd11);
         border:1px solid #1f6feb44; border-radius:10px;
         padding:14px 18px; margin-bottom:12px;">
      <h3 style="margin:0;color:#58a6ff;">📡 Sensor S{idx+1} — Profundidad {prof}</h3>
      <p style="margin:0;color:#8b949e;font-size:0.85rem;">
        Estación: <b style="color:#e6edf3">{id_proyecto}</b> &nbsp;|&nbsp;
        Lectura al corte: <b style="color:#e6edf3">{fecha_lectura_str}</b>
      </p>
    </div>
    """, unsafe_allow_html=True)

    m1, m1_g, m2, m3, m4 = st.columns(5)
    if ultimo_registro is not None:
        vwc_val_str = safe_val(ultimo_registro, cv) if cv else "N/D"
        gwc_val_str = calcular_gwc(vwc_val_str, densidad)
        with m1:   st.metric("💧 Humedad VWC",       f"{vwc_val_str} %"    if cv else "N/D")
        with m1_g: st.metric("🌾 Humedad GWC",       f"{gwc_val_str} %"    if cv else "N/D")
        with m2:   st.metric("🌡️ Temperatura",        f"{safe_val(ultimo_registro, ct, 1)} °C" if ct else "N/D")
        with m3:   st.metric("⚡ Presión de Poros",   f"{safe_val(ultimo_registro, cp, 0)} mbar" if cp else "N/D")
        with m4:   st.metric("📏 Nivel Hidrostático", f"{safe_val(ultimo_registro, cd, 1)} cm"  if cd else "N/D")
    else:
        st.warning("No se encontraron registros de telemetría.")

    st.markdown("---")
    st.markdown(f"#### 📊 Gráfica de Tendencia — {variable_grafico} (Ventana de 7 días)")

    fecha_max = pd.to_datetime(fecha_sel) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    fecha_min = pd.to_datetime(fecha_sel) - pd.Timedelta(days=7)
    df_f = df_data[
        (df_data['TIMESTAMP'] >= fecha_min) &
        (df_data['TIMESTAMP'] <= fecha_max)
    ].copy()

    mapeo = {
        "Humedad (VWC %)":               cv,
        "Humedad Gravimétrica (GWC %)":  cv,
        "Temperatura (°C)":              ct,
        "Presión de Celda (mbar)":       cp,
        "Nivel (cm)":                    cd,
    }
    col_obj = mapeo.get(variable_grafico)

    if col_obj and col_obj in df_f.columns:
        df_g = df_f[['TIMESTAMP', col_obj]].dropna().copy()
        df_g.columns = ['Fecha', variable_grafico]
        df_g['Fecha'] = pd.to_datetime(df_g['Fecha'])
        if variable_grafico == "Humedad Gravimétrica (GWC %)":
            df_g[variable_grafico] = df_g[variable_grafico].astype(float) / densidad
        if not df_g.empty:
            fig = px.line(df_g, x='Fecha', y=variable_grafico, template="plotly_dark")
            fig.update_traces(line=dict(color='#388bfd', width=2.5))
            fig.update_layout(
                margin=dict(l=50, r=20, t=20, b=40),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=True, gridcolor='#21262d', title=None, tickformat='%d %b\n%H:%M'),
                yaxis=dict(showgrid=True, gridcolor='#21262d', title=None,
                           rangemode='nonnegative' if "Humedad" in variable_grafico else 'normal'),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.dataframe(df_g, use_container_width=True, hide_index=True)
            csv_bytes = df_g.set_index('Fecha').to_csv().encode("utf-8")
            st.download_button(
                "⬇️ Exportar serie completa (CSV)", data=csv_bytes,
                file_name=f"{id_proyecto}_S{idx+1}_{variable_grafico.replace(' ', '_')}.csv",
                mime="text/csv", use_container_width=True,
            )
        else:
            st.warning("⚠️ No hay puntos de datos válidos en este rango.")
    else:
        st.error("⚠️ La variable seleccionada no está instrumentada en este sensor.")

    if st.button("Cerrar", key=f"close_hist_{id_proyecto}_{idx}", use_container_width=True):
        st.rerun()


# ─────────────────────────────────────────────
# 6. PANEL POR PROYECTO (actualizado)
# ─────────────────────────────────────────────
def construir_interfaz_proyecto(id_proyecto: str):
    cfg = CONFIG_PROYECTOS[id_proyecto]
    densidad = cfg["densidad"]

    df_data, error = cargar_datos_proyecto(id_proyecto)
    if error or df_data is None:
        st.error(error)
        return

    rain_val, bat_val = cargar_pluviometro_bateria(id_proyecto)

    n         = cfg["max_sensores"]
    cols_vwc  = get_cols(df_data, "VWC",  n)
    cols_temp = get_cols(df_data, "TEMP", n)
    cols_pt   = get_cols(df_data, "PT",   n)
    cols_dpt  = get_cols(df_data, "DPT",  n)

    # Selector de fecha
    fechas_disponibles = sorted(df_data['TIMESTAMP'].dt.date.unique(), reverse=True) \
        if not df_data.empty else []
    fecha_sel = st.selectbox(
        "📅 Fecha activa de simulación:",
        options=fechas_disponibles,
        key=f"sb_date_{id_proyecto}"
    )

    df_dia = df_data[df_data['TIMESTAMP'].dt.date == fecha_sel]
    if df_dia.empty:
        st.warning("⚠️ Sin registros para el día seleccionado.")
        return
    ultimo = df_dia.iloc[-1]

    # Sensor seleccionado (persiste en session_state)
    key_idx = f"sensor_sel_{id_proyecto}"
    if key_idx not in st.session_state:
        st.session_state[key_idx] = 0
    sel_idx = st.session_state[key_idx]

    # ── NUEVO: render del perfil HTML ──────────────────────────────────────
    n_sens     = cfg["max_sensores"]
    iframe_h   = 110 + n_sens * 72 + 60
    html_code  = render_soil_profile(
        id_proyecto, cfg, cols_vwc, cols_temp, cols_pt, cols_dpt,
        ultimo, rain_val, bat_val, selected_idx=sel_idx,
    )
    st.components.v1.html(html_code, height=iframe_h, scrolling=False)

    # ── Botones de acción debajo del perfil ────────────────────────────────
    col_hist, col_exp = st.columns(2)
    cv_sel = cols_vwc[sel_idx] if sel_idx < len(cols_vwc) else None
    ct_sel = cols_temp[sel_idx] if sel_idx < len(cols_temp) else None
    cp_sel = cols_pt[sel_idx]   if sel_idx < len(cols_pt)   else None
    cd_sel = cols_dpt[sel_idx]  if sel_idx < len(cols_dpt)  else None

    with col_hist:
        if st.button("📈 Ver Histórico del Sensor Activo", key=f"hist_{id_proyecto}", use_container_width=True):
            modal_historico(
                id_proyecto=id_proyecto, idx=sel_idx,
                df_data=df_data,
                cols_vwc=cols_vwc, cols_temp=cols_temp,
                cols_pt=cols_pt, cols_dpt=cols_dpt
            )
    with col_exp:
        fila_export = ultimo[[c for c in [cv_sel, ct_sel, cp_sel, cd_sel, 'TIMESTAMP'] if c]]
        st.download_button(
            "⬇️ Exportar lectura del día",
            data=pd.DataFrame([fila_export]).to_csv(index=False).encode("utf-8"),
            file_name=f"{id_proyecto}_S{sel_idx+1}_{fecha_sel}.csv",
            mime="text/csv", use_container_width=True,
        )

    # ── Tabla resumen expandible ───────────────────────────────────────────
    with st.expander("📊 Ver tabla completa de sensores"):
        resumen = []
        for i in range(n):
            cv_i  = cols_vwc[i]  if i < len(cols_vwc)  else None
            vwc_i = safe_val(ultimo, cv_i) if cv_i else "N/D"
            resumen.append({
                "Sensor":         f"S{i+1}",
                "Profundidad":    fmt_depth(cv_i) if cv_i else "N/A",
                "VWC (%)":        vwc_i,
                "GWC (%)":        calcular_gwc(vwc_i, densidad),
                "Temp (°C)":      safe_val(ultimo, cols_temp[i], 1) if i < len(cols_temp) else "N/D",
                "Presión (mbar)": safe_val(ultimo, cols_pt[i], 0)   if i < len(cols_pt)   else "N/D",
                "Nivel (cm)":     safe_val(ultimo, cols_dpt[i], 1)  if i < len(cols_dpt)  else "N/D",
            })
        st.dataframe(pd.DataFrame(resumen), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# 7. ANÁLISIS AVANZADO (sin cambios funcionales)
# ─────────────────────────────────────────────
def construir_analisis_avanzado():
    st.subheader("📊 Panel de Análisis Avanzado e Histórico")
    st.markdown("Filtra ventanas de tiempo extendidas y visualiza el comportamiento de todas las profundidades simultáneamente.")

    col_proj, col_time, col_var = st.columns(3)
    with col_proj:
        _opciones_estacion = {"Relave A": "DRF", "Relave B": "ROMERAL"}
        _nombre_sel = st.selectbox("Estación de monitoreo", list(_opciones_estacion.keys()), key="adv_proj_sel")
        proyecto_sel = _opciones_estacion[_nombre_sel]
        cfg_adv   = CONFIG_PROYECTOS[proyecto_sel]
        densidad_adv = cfg_adv["densidad"]
    with col_time:
        rango_tiempo = st.selectbox(
            "Rango Temporal (Eje X)",
            ["Últimos 7 días", "Últimos 30 días", "Últimos 90 días", "Histórico Completo"],
            index=1, key="adv_time_sel"
        )
    with col_var:
        variable_analisis = st.selectbox(
            "Métrica a graficar",
            ["Humedad VWC (%)", "Humedad Gravimétrica GWC (%)", "Presión de Poros (mbar)", "Temperatura (°C)"],
            key="adv_var_sel"
        )

    df_adv_raw, err_adv = cargar_datos_proyecto(proyecto_sel)
    if err_adv or df_adv_raw is None:
        st.error(f"No se pudieron cargar los datos históricos para {_nombre_sel}.")
        return

    n_adv         = cfg_adv["max_sensores"]
    cols_vwc_adv  = get_cols(df_adv_raw, "VWC",  n_adv)
    cols_temp_adv = get_cols(df_adv_raw, "TEMP", n_adv)
    cols_pt_adv   = get_cols(df_adv_raw, "PT",   n_adv)

    sensores_disponibles   = [f"S{i+1}" for i in range(n_adv)]
    sensores_seleccionados = st.multiselect(
        "Seleccionar Sensores en Pantalla",
        options=sensores_disponibles, default=sensores_disponibles,
        key="adv_sensors_multiselect"
    )

    hoy = df_adv_raw['TIMESTAMP'].max() if not df_adv_raw.empty else pd.Timestamp.now()
    deltas = {
        "Últimos 7 días": 7, "Últimos 30 días": 30,
        "Últimos 90 días": 90
    }
    fecha_limite = hoy - pd.Timedelta(days=deltas[rango_tiempo]) \
        if rango_tiempo in deltas else df_adv_raw['TIMESTAMP'].min()
    df_adv_filtrado = df_adv_raw[df_adv_raw['TIMESTAMP'] >= fecha_limite].sort_values('TIMESTAMP').copy()

    mapeo_prefijo = {
        "Humedad VWC (%)":               (cols_vwc_adv,  "VWC"),
        "Humedad Gravimétrica GWC (%)":  (cols_vwc_adv,  "GWC"),
        "Presión de Poros (mbar)":       (cols_pt_adv,   "Presión"),
        "Temperatura (°C)":              (cols_temp_adv, "Temp"),
    }
    lista_columnas, label_y = mapeo_prefijo[variable_analisis]

    fig_adv = go.Figure()
    for idx_s, s_name in enumerate(sensores_disponibles):
        if s_name in sensores_seleccionados and idx_s < len(lista_columnas):
            col_real = lista_columnas[idx_s]
            if col_real in df_adv_filtrado.columns:
                df_s = df_adv_filtrado[['TIMESTAMP', col_real]].dropna().copy()
                if not df_s.empty:
                    y_vals = df_s[col_real].astype(float) / densidad_adv \
                        if variable_analisis == "Humedad Gravimétrica GWC (%)" \
                        else df_s[col_real]
                    fig_adv.add_trace(go.Scatter(
                        x=df_s['TIMESTAMP'], y=y_vals, mode='lines',
                        name=f"{s_name} ({fmt_depth(col_real)})",
                        line=dict(width=2),
                        hovertemplate=f'<b>{s_name}</b><br>Fecha: %{{x}}<br>{label_y}: %{{y:.2f}}<extra></extra>'
                    ))

    fig_adv.update_layout(
        template="plotly_dark", paper_bgcolor="#161b22",
        plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=50, r=30, t=30, b=50),
        xaxis=dict(showgrid=True, gridcolor="#21262d", title=None),
        yaxis=dict(title=variable_analisis, showgrid=True, gridcolor="#21262d"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=520
    )
    st.plotly_chart(fig_adv, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 📥 Exportar Datos Combinados")
    df_export_list = []
    for idx_s, s_name in enumerate(sensores_disponibles):
        if s_name in sensores_seleccionados and idx_s < len(lista_columnas):
            col_real = lista_columnas[idx_s]
            if col_real in df_adv_filtrado.columns:
                df_s = df_adv_filtrado[['TIMESTAMP', col_real]].copy()
                df_s[s_name] = df_s[col_real].astype(float) / densidad_adv \
                    if variable_analisis == "Humedad Gravimétrica GWC (%)" \
                    else df_s[col_real]
                df_export_list.append(df_s[['TIMESTAMP', s_name]].set_index('TIMESTAMP'))
    if df_export_list:
        df_final_export = pd.concat(df_export_list, axis=1).reset_index()
        st.download_button(
            label=f"⬇️ Descargar Datos de {_nombre_sel} (CSV)",
            data=df_final_export.to_csv(index=False).encode('utf-8'),
            file_name=f"analisis_{_nombre_sel.replace(' ', '_')}_{label_y.lower().replace(' ', '_')}.csv",
            mime="text/csv", use_container_width=True
        )


# ─────────────────────────────────────────────
# 8. SISTEMA DE PESTAÑAS GLOBAL
# ─────────────────────────────────────────────
tab_monitoreo, tab_avanzado = st.tabs([
    "📍 Monitoreo en Tiempo Real",
    "📊 Análisis Avanzado"
])

with tab_monitoreo:
    tab_drf, tab_romeral = st.tabs([
        "📍 Relave A",
        "📍 Relave B",
    ])
    with tab_drf:
        construir_interfaz_proyecto("DRF")
    with tab_romeral:
        construir_interfaz_proyecto("ROMERAL")

with tab_avanzado:
    construir_analisis_avanzado()
