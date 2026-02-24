import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import qrcode
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84

# ==========================================
# 1. CORE ENGINE
# ==========================================
@st.cache_resource
def init_satellite_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_satellite_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:,.2f} KM/H",
    }
    for i in range(36): tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # Trajectory (Past 100 Minutes)
    lats, lons = [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        ps = wgs84.subpoint(sat_obj.at(pt))
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)

    return {
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "RAW_TELE": tele
    }

# ==========================================
# 2. PDF ENGINE
# ==========================================
def build_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "STRATEGIC DATA ARCHIVE", ln=True, align='C')
    
    # 5-Level Address Header
    pdf.set_font("Arial", 'B', 8)
    addr_str = f"ZONE: {addr['z']} | CNTR: {addr['c']} | PROV: {addr['p']} | DIST: {addr['d']} | SUB: {addr['s']}"
    pdf.cell(0, 8, addr_str.upper(), border=1, ln=True, align='C')
    
    # Telemetry Table
    items = list(m['RAW_TELE'].items())
    pdf.ln(5)
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("Courier", '', 7)
                pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    # QR & Sig
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 20, 230, 30, 30)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 140, 235, 30, 20)
    
    pdf.set_xy(110, 260); pdf.set_font("Arial", 'B', 10); pdf.cell(80, 5, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("Arial", 'I', 8); pdf.cell(80, 5, s_pos.upper(), align='C')

    # Encrypt
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE
# ==========================================
st.set_page_config(page_title="ZENITH V7.6", layout="wide")

# Initialize State Keys
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'm_id' not in st.session_state: st.session_state.m_id = ""
if 'm_pwd' not in st.session_state: st.session_state.m_pwd = ""

with st.sidebar:
    st.header("🛰️ COMMAND PANEL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()) if sat_catalog else ["Loading..."])
    
    st.subheader("📍 ADDRESS")
    addr_data = {
        "z": st.text_input("Zone", "Asia"),
        "c": st.text_input("Country", "Thailand"),
        "p": st.text_input("Province", "Bangkok"),
        "d": st.text_input("District", "Phra Nakhon"),
        "s": st.text_input("Sub-District", "Phra Borom")
    }

    st.divider()
    st.subheader("🔍 MULTI-ZOOM")
    z1 = st.slider("Tactical", 1, 18, 12)
    z2 = st.slider("Global", 1, 10, 2)
    z3 = st.slider("Station", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.open_sys = True

@st.dialog("📋 MISSION ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            t_sel = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
            
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Designation", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        
        if st.button("BUILD ENCRYPTED ARCHIVE"):
            fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%m%d')}"
            pwd = "123456"
            m_data = run_calculation(sat_catalog[sel_sat], t_sel)
            st.session_state.pdf_blob = build_archive(sel_sat, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id = fid
            st.session_state.m_pwd = pwd
            st.rerun()
    else:
        # FIXED: Use session_state directly with safe fallback
        mid = st.session_state.get('m_id', 'N/A')
        mpw = st.session_state.get('m_pwd', 'N/A')
        st.success(f"ID: {mid} | PASS: {mpw}")
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{mid}.pdf")
        if st.button("CLOSE"):
            st.session_state.open_sys = False
            st.session_state.pdf_blob = None
            st.rerun()

if st.session_state.open_sys: archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="text-align:center; background:white; border:5px solid black; padding:10px; border-radius:100px; margin-bottom:20px;">
                <span style="color:black; font-size:50px; font-weight:900; font-family:monospace;">{datetime.now().strftime("%H:%M:%S")}</span></div>''', unsafe_allow_html=True)
    
    if sat_catalog and sel_sat in sat_catalog:
        m = run_calculation(sat_catalog[sel_sat])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("ALTITUDE", f"{m['ALT_VAL']:,.2f} KM")
        c2.metric("VELOCITY", f"{m['VEL_VAL']:,.0f} KM/H")
        c3.metric("COORD", m["COORD"])
        
        st.subheader("🌍 GEOSPATIAL COMMAND")
        m_cols = st.columns(3)
        
        def draw_map(lt, ln, zm, k, tl, tn):
            fig = go.Figure()
            if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
            fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)

        with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
        with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
        with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], [])

        st.subheader("📊 TELEMETRY")
        st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()