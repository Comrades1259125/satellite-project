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
# 1. CORE DATA ENGINE (WITH TRAJECTORY)
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
    # Support for both Live and Predictive
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # 40-Parameter Telemetry Grid
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:,.2f} KM/H",
        "EPS_BATT": f"{random.uniform(28, 32):.2f} V",
        "OBC_TEMP": f"{random.uniform(22, 28):.2f} C",
        "COM_SNR": f"{random.uniform(18, 24):.2f} dB",
        "SYS_STAT": "NOMINAL"
    }
    for i in range(32): tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # RECOVERY: Trajectory Path (Past 100 Minutes)
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
# 2. PDF ENGINE (WITH SIGNATURE & SEAL)
# ==========================================
class MISSION_PDF(FPDF):
    def draw_graph_restored(self, x, y, w, h, title, data, color):
        self.set_fill_color(250, 250, 250); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.5); self.rect(x, y, w, h)
        self.set_font("Arial", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = MISSION_PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 22); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    
    # Address Row (5 Levels)
    pdf.set_font("Arial", 'B', 8)
    addr_text = f"ZONE: {addr['z']} | CNTR: {addr['c']} | PROV: {addr['p']} | DIST: {addr['d']} | SUB: {addr['s']}"
    pdf.cell(0, 8, addr_text.upper(), border=1, ln=True, align='C')
    pdf.ln(5)

    # Telemetry Table
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("Courier", '', 7)
                pdf.cell(47.5, 8, f" {items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    # Graphs Page
    pdf.add_page()
    pdf.draw_graph_restored(20, 30, 170, 70, "ORBITAL LATITUDE TRACK", m['TAIL_LAT'], (0, 80, 180))
    
    # QR & Signature Restoration
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 20, 190, 40, 40)
    
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 140, 200, 35, 25) # SEAL
    pdf.line(110, 230, 190, 230)
    pdf.set_xy(110, 232); pdf.set_font("Arial", 'B', 11); pdf.cell(80, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("Arial", 'I', 9); pdf.cell(80, 5, s_pos.upper(), align='C')

    # Encryption
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (TRIPLE ZOOM & ADDRESS)
# ==========================================
st.set_page_config(page_title="ZENITH V7.5", layout="wide")

if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'open_sys' not in st.session_state: st.session_state.open_sys = False

with st.sidebar:
    st.header("🛰️ COMMAND PANEL")
    if sat_catalog:
        sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()))
        sat_obj = sat_catalog[sel_sat]
    
    st.subheader("📍 ADDRESS CONFIG")
    z_a = st.text_input("Zone", "Asia")
    c_a = st.text_input("Country", "Thailand")
    p_a = st.text_input("Province", "Bangkok")
    d_a = st.text_input("District", "Phra Nakhon")
    s_a = st.text_input("Sub-District", "Phra Borom")
    addr_data = {"z": z_a, "c": c_a, "p": p_a, "d": d_a, "s": s_a}

    st.divider()
    st.subheader("🔍 TRIPLE ZOOM CONTROL")
    z1 = st.slider("Tactical (Local)", 1, 18, 12)
    z2 = st.slider("Global (Orbit)", 1, 10, 2)
    z3 = st.slider("Station (Ground)", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.open_sys = True

@st.dialog("📋 MISSION ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        # RESTORED: Predictive Calculation
        mode = st.radio("Calculation Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            col1, col2 = st.columns(2)
            d = col1.date_input("Target Date")
            t = col2.time_input("Target Time")
            t_sel = datetime.combine(d, t).replace(tzinfo=timezone.utc)
            
        st.divider()
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Designation", "CHIEF COMMANDER")
        s_img = st.file_uploader("Official Seal (PNG)", type=['png'])
        
        if st.button("BUILD ENCRYPTED ARCHIVE", use_container_width=True):
            fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%m%d')}"
            pwd = "123456"
            m_data = run_calculation(sat_obj, t_sel)
            st.session_state.pdf_blob = build_archive(sel_sat, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.success(f"ID: {st.session_state.m_id} | PASS: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf")
        if st.button("BACK"): st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.open_sys: archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    # Dynamic Clock (Sync to Local)
    st.markdown(f'''<div style="text-align:center; background:white; border:5px solid black; padding:10px; border-radius:100px; margin-bottom:20px;">
                <span style="color:black; font-size:50px; font-weight:900; font-family:monospace;">{datetime.now().strftime("%H:%M:%S")}</span></div>''', unsafe_allow_html=True)
    
    m = run_calculation(sat_obj)
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT_VAL']:,.2f} KM")
    c2.metric("VELOCITY", f"{m['VEL_VAL']:,.0f} KM/H")
    c3.metric("COORDINATES", m["COORD"])
    
    # RESTORED: Triple Map View with Trails
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
    with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], []) # Ground Station

    st.subheader("📊 TELEMETRY DATA (40 PARAMS)")
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog: dashboard()