import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import qrcode
import time
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84
from PIL import Image

# ==========================================
# 1. CORE ENGINE & TELEMETRY
# ==========================================
@st.cache_resource
def init_system():
    try:
        data = load.tle_file('https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle')
        return {s.name: s for s in data}
    except:
        return {}

assets = init_system()
ts = load.timescale()

def get_metrics(sat_obj):
    now = datetime.now(timezone.utc)
    t = ts.from_datetime(now)
    geocentric = sat_obj.at(t)
    sub = wgs84.subpoint(geocentric)
    
    telemetry = {
        "LATITUDE": f"{sub.latitude.degrees:.4f}",
        "LONGITUDE": f"{sub.longitude.degrees:.4f}",
        "ALTITUDE": f"{sub.elevation.km:.2f} KM",
        "VELOCITY": f"{np.linalg.norm(geocentric.velocity.km_per_s)*3600:,.1f} KM/H",
        "BATT_LEVEL": f"{random.uniform(94, 98):.2f}%",
        "CORE_TEMP": f"{random.uniform(22, 26):.2f}C",
        "SIGNAL_SNR": f"{random.uniform(19, 23):.1f}dB",
        "UPLINK_STAT": "ACTIVE"
    }
    # Fill remaining to 40 params
    for i in range(32): telemetry[f"SENS_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"
    
    return telemetry, sub.latitude.degrees, sub.longitude.degrees

# ==========================================
# 2. PDF ARCHIVE SYSTEM (STYLIZED)
# ==========================================
def create_pdf(fid, key, sat_name, metrics, addr_data):
    pdf = FPDF()
    pdf.add_page()
    # Header
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(0, 15, "OFFICIAL DATA ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"ARCHIVE ID: {fid}", ln=True, align='C')
    
    # Address Grid (4 Columns)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    cols = list(addr_data.values())
    for i in range(4):
        pdf.cell(47.5, 10, cols[i].upper(), border=1, align='C')
    pdf.ln(15)

    # Data Table
    pdf.set_font("Courier", '', 8)
    items = list(metrics.items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.cell(47.5, 7, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    # Encryption Key Footer
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"ENCRYPTION KEY: {key}", ln=True, align='C')

    # Security Encryption
    raw = BytesIO(pdf.output())
    writer = PdfWriter()
    for page in PdfReader(raw).pages: writer.add_page(page)
    writer.encrypt(key)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()

# ==========================================
# 3. COMMAND INTERFACE
# ==========================================
st.set_page_config(page_title="STRATEGIC DASHBOARD", layout="wide")

# Sidebar Configuration
with st.sidebar:
    st.header("🛰️ SATELLITE CONTROL")
    target = st.selectbox("SELECT ASSET", list(assets.keys()) if assets else ["No Data"])
    
    st.subheader("📍 DEPLOYMENT ADDRESS")
    a1 = st.text_input("Region", "ASIA-PACIFIC")
    a2 = st.text_input("Sector", "SEC-07")
    a3 = st.text_input("Node", "BKK-MAIN")
    a4 = st.text_input("Level", "LVL-04")
    addr_map = {"R": a1, "S": a2, "N": a3, "L": a4}

    st.divider()
    st.subheader("🔍 MULTI-ZOOM")
    z1 = st.slider("Tactical", 1, 18, 12)
    z2 = st.slider("Global", 1, 10, 2)
    z3 = st.slider("Station", 1, 18, 15)

    if st.button("GENERATE OFFICIAL ARCHIVE", use_container_width=True, type="primary"):
        st.session_state.show_modal = True

# Main Dashboard Fragment (Real-time Clock & Maps)
@st.fragment(run_every=1.0)
def main_view():
    # Clock synchronized to Local Timezone
    local_time = datetime.now().strftime("%H:%M:%S")
    st.markdown(f"""
        <div style="background:white; padding:20px; border-radius:100px; text-align:center; border:5px solid black; margin-bottom:20px;">
            <h1 style="color:black; margin:0; font-family:monospace; font-size:60px;">{local_time}</h1>
        </div>
    """, unsafe_allow_html=True)

    if assets and target in assets:
        m, lat, lon = get_metrics(assets[target])
        
        # Metrics Row
        c1, c2, c3 = st.columns(3)
        c1.metric("ALTITUDE", m["ALTITUDE"])
        c2.metric("VELOCITY", m["VELOCITY"])
        c3.metric("COORD", f"{m['LATITUDE']}, {m['LONGITUDE']}")

        # Triple Map View
        st.subheader("🌍 GEOSPATIAL COMMAND")
        m_cols = st.columns(3)
        
        def draw_map(lt, ln, zm, key):
            fig = go.Figure(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=key)

        with m_cols[0]: draw_map(lat, lon, z1, "m1")
        with m_cols[1]: draw_map(lat, lon, z2, "m2")
        with m_cols[2]: draw_map(13.75, 100.5, z3, "m3") # Station Map

        # 40 Params Table
        st.subheader("📊 SYSTEM TELEMETRY (40-STREAM)")
        df = pd.DataFrame([list(m.items())[i:i+4] for i in range(0, 40, 4)])
        st.table(df)

# Archive Modal (Matches your Screenshot)
if st.session_state.get("show_modal"):
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def show_archive():
        # Matching your screenshot ID and Key
        fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%m%d')}"
        key = "".join([str(random.randint(0,9)) for _ in range(6)])
        
        st.markdown(f"""
            <div style="text-align:center; background:white; padding:30px; border-radius:10px; border:1px solid #ddd;">
                <p style="color:grey; font-weight:bold;">DOCUMENT ARCHIVE ID</p>
                <h2 style="color:red; font-weight:900; letter-spacing:2px;">{fid}</h2>
                <hr>
                <p style="color:grey; font-weight:bold;">ENCRYPTION KEY</p>
                <h1 style="color:black; font-weight:900; letter-spacing:10px;">{key}</h1>
            </div>
        """, unsafe_allow_html=True)
        
        m_data, _, _ = get_metrics(assets[target])
        pdf_data = create_pdf(fid, key, target, m_data, addr_map)
        
        st.download_button("📥 DOWNLOAD ENCRYPTED ARCHIVE", pdf_data, f"{fid}.pdf", use_container_width=True)
        if st.button("RETURN TO COMMAND", use_container_width=True):
            st.session_state.show_modal = False
            st.rerun()
    show_archive()

main_view()