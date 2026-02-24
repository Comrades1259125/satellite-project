import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
import qrcode
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84
from PIL import Image, ImageDraw

# ==========================================
# 1. ANALYTICS & PREDICTION ENGINE
# ==========================================
@st.cache_resource
def system_initialize():
    try:
        data = load.tle_file('https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle')
        return {s.name: s for s in data}
    except Exception as e:
        st.error(f"Link Dropout: {e}")
        return {}

assets = system_initialize()
timescale = load.timescale()

def calculate_zenith_metrics(asset_obj, ref_time=None):
    now = ref_time if ref_time else datetime.now(timezone.utc)
    t = timescale.from_datetime(now)
    pos = asset_obj.at(t)
    sub = wgs84.subpoint(pos)
    vel = np.linalg.norm(pos.velocity.km_per_s)
    
    # 40 Unique Logic Sensors (No repetition)
    telemetry_stream = {
        "GEO_LAT": f"{sub.latitude.degrees:.4f}",
        "GEO_LON": f"{sub.longitude.degrees:.4f}",
        "GEO_ALT": f"{sub.elevation.km:.2f}",
        "VEL_KPH": f"{vel * 3600:,.1f}",
        "PWR_SOLAR": f"{random.uniform(400, 600):.2f} W",
        "PWR_BATT": f"{random.uniform(92, 99):.1f} %",
        "THERM_CORE": f"{random.uniform(18, 24):.2f} C",
        "CPU_CYCLE": f"{random.randint(15, 30)} %",
        "SIG_NOISE": f"{random.uniform(18, 25):.2f} dB",
        "LINK_UP": "STABLE",
        "ENC_MODE": "ENHANCED",
        "FUEL_LVL": f"{random.uniform(60, 85):.1f} %"
    }
    for i in range(28): telemetry_stream[f"AUX_{i+1:02d}"] = f"{random.uniform(5, 95):.2f}"

    # PROJECTION Logic (Future Path 60 mins) - Replaces "Tail" logic
    proj_lat, proj_lon = [], []
    for m in range(0, 61, 5):
        future_t = timescale.from_datetime(now + timedelta(minutes=m))
        future_sub = wgs84.subpoint(asset_obj.at(future_t))
        proj_lat.append(future_sub.latitude.degrees)
        proj_lon.append(future_sub.longitude.degrees)

    return {
        "INFO": telemetry_stream,
        "LAT": sub.latitude.degrees, "LON": sub.longitude.degrees,
        "ALT": sub.elevation.km, "VEL": vel * 3600,
        "PROJ_LAT": proj_lat, "PROJ_LON": proj_lon
    }

# ==========================================
# 2. STRATEGIC ARCHIVE GENERATOR
# ==========================================
class STRATEGIC_PDF(FPDF):
    def add_data_grid(self, data_dict):
        self.set_font("Courier", 'B', 8)
        x_start, y_start = 10, 50
        count = 0
        for k, v in data_dict.items():
            col = count % 4
            row = count // 4
            self.set_xy(x_start + (col * 48), y_start + (row * 8))
            self.cell(48, 8, f"{k}:{v}", border=1)
            count += 1

    def insert_visual(self, x, y, w, h, title, lats, lons):
        self.rect(x, y, w, h)
        self.set_font("Arial", 'B', 10)
        self.text(x, y-2, title)
        # Simplified vector path drawing
        if lats:
            self.set_draw_color(200, 0, 0)
            for i in range(len(lats)-1):
                self.line(x + (lons[i]+180)*(w/360), (y+h) - (lats[i]+90)*(h/180),
                          x + (lons[i+1]+180)*(w/360), (y+h) - (lats[i+1]+90)*(h/180))

def create_secure_archive(name, loc, s_name, s_pos, seal, fid, pin, metrics):
    pdf = STRATEGIC_PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, "ZENITH COMMAND ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", 'I', 10); pdf.cell(0, 8, f"ASSET: {name} | NODE: {loc.upper()} | REF: {fid}", ln=True, align='C')
    pdf.add_data_grid(metrics["INFO"])
    
    pdf.add_page()
    pdf.insert_visual(20, 30, 170, 80, "PROJECTED ORBITAL SWATH", metrics["PROJ_LAT"], metrics["PROJ_LON"])
    
    qr = qrcode.make(fid).convert('RGB')
    q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 15, 220, 35, 35)
    
    if seal: pdf.image(BytesIO(seal.getvalue()), 150, 220, 30, 20)
    pdf.set_xy(110, 245); pdf.set_font("Arial", 'B', 11); pdf.cell(80, 5, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("Arial", '', 9); pdf.cell(80, 5, s_pos.upper(), align='C')

    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pin); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. ZENITH COMMAND INTERFACE
# ==========================================
st.set_page_config(page_title="ZENITH V7.0", layout="wide")

if 'archive' not in st.session_state: st.session_state.archive = None
if 'trigger' not in st.session_state: st.session_state.trigger = False

with st.sidebar:
    st.title("🛰️ ZENITH COMMAND")
    target = st.selectbox("ACTIVE ASSET", list(assets.keys()))
    node = st.text_input("COMMAND NODE", "PACIFIC-ALPHA")
    st.divider()
    st.subheader("MULTIVARIATE ZOOM")
    z_local = st.slider("Tactical View", 1, 18, 12)
    z_global = st.slider("Orbital View", 1, 10, 2)
    z_node = st.slider("Node View", 1, 18, 14)
    if st.button("LOCK & ARCHIVE", use_container_width=True, type="primary"): st.session_state.trigger = True

@st.dialog("🔐 SECURITY VERIFICATION")
def auth_dialog():
    if not st.session_state.archive:
        u_name = st.text_input("Officer Name", "AGENT TRIN")
        u_rank = st.text_input("Designation", "COMMANDER")
        u_seal = st.file_uploader("Auth Seal (PNG)", type=['png'])
        if st.button("ENCRYPT DATA"):
            ref = f"ZNTH-{random.randint(1000,9999)}"
            pin = "123456"
            m = calculate_zenith_metrics(assets[target])
            st.session_state.archive = create_secure_archive(target, node, u_name, u_rank, u_seal, ref, pin, m)
            st.session_state.ref_id = ref; st.rerun()
    else:
        st.info(f"VERIFIED ID: {st.session_state.ref_id}")
        st.download_button("DOWNLOAD ENCRYPTED ARCHIVE", st.session_state.archive, f"{st.session_state.ref_id}.pdf")
        if st.button("DISCONNECT"): 
            st.session_state.trigger = False; st.session_state.archive = None; st.rerun()

if st.session_state.trigger: auth_dialog()

@st.fragment(run_every=1.0)
def live_dashboard():
    # Dynamic Digital Clock
    st.markdown(f'''<div style="background:#000; color:#0f0; padding:15px; border-radius:15px; text-align:center; border:2px solid #333; margin-bottom:20px;">
                <span style="font-size:45px; font-family:monospace; font-weight:bold;">{datetime.now(timezone.utc).strftime("%H:%M:%S")} UTC</span></div>''', unsafe_allow_html=True)
    
    m = calculate_zenith_metrics(assets[target])
    
    # Core Analytics Metrics
    row1 = st.columns(3)
    row1[0].metric("ZENITH ALTITUDE", f"{m['ALT']:,.2f} KM")
    row1[1].metric("ORBITAL VELOCITY", f"{m['VEL']:,.1f} KM/H")
    row1[2].metric("SUB-SATELLITE PT", f"{m['LAT']:.2f}, {m['LON']:.2f}")

    # Triple Map Logic
    st.subheader("🌐 MULTI-VECTOR GEOSPATIAL ANALYSIS")
    maps = st.columns(3)
    
    def generate_map(lt, ln, zm, tag, plat, plon):
        fig = go.Figure()
        # Drawing the Predicted Projection Path
        fig.add_trace(go.Scattermapbox(lat=plat, lon=plon, mode='lines', line=dict(width=2, color='cyan')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red', symbol='rocket')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=tag)

    with maps[0]: generate_map(m['LAT'], m['LON'], z_local, "TACT", m["PROJ_LAT"], m["PROJ_LON"])
    with maps[1]: generate_map(m['LAT'], m['LON'], z_global, "GLOB", m["PROJ_LAT"], m["PROJ_LON"])
    with maps[2]: generate_map(13.75, 100.5, z_node, "NODE", [], []) # Centered on Station

    # Telemetry Table
    st.subheader("📋 TELEMETRY DATA GRID")
    st.table(pd.DataFrame([list(m["INFO"].items())[i:i+4] for i in range(0, 40, 4)]))

if assets: live_dashboard()