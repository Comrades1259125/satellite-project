import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
import qrcode
from io import BytesIO
from skyfield.api import load, wgs84
from geopy.geocoders import Nominatim

# --- CORE ENGINE (ห้ามเปลี่ยน) ---
@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()
geolocator = Nominatim(user_agent="v5950_stable_final")

def run_calculation(sat_obj, st_lat, st_lon, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    station = wgs84.latlon(st_lat, st_lon)
    alt, az, distance = (sat_obj - station).at(t).altaz()
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}", "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "SIG_ELEV": f"{alt.degrees:.2f} DEG", "OBC_STATUS": "ACTIVE" if alt.degrees > -5 else "SLEEP"
    }
    for i in range(16): tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"
    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "FOOTPRINT": np.sqrt(2 * 6371 * subpoint.elevation.km), "RAW_TELE": tele}

# --- PDF GENERATOR (WITH SIGNATURE & SEAL) ---
def build_pdf(sat_name, addr_dict, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 20)
    pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 8); pdf.set_fill_color(30, 30, 40); pdf.set_text_color(255, 255, 255)
    f_addr = f"{addr_dict['sub']}, {addr_dict['dist']}, {addr_dict['prov']}, {addr_dict['cntr']}".upper()
    pdf.cell(0, 10, f" ASSET: {sat_name} | STATION: {f_addr}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(5)
    for k, v in m['RAW_TELE'].items():
        pdf.set_font("helvetica", 'B', 8); pdf.cell(40, 6, f"{k}:", border=1)
        pdf.set_font("helvetica", '', 8); pdf.cell(50, 6, f"{v}", border=1, ln=True)
    pdf.ln(20); pdf.line(120, 240, 190, 240)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), x=140, y=215, w=30)
    pdf.set_xy(120, 242); pdf.set_font("helvetica", 'B', 10); pdf.cell(70, 7, s_name.upper(), align='C', ln=True)
    pdf.set_x(120); pdf.cell(70, 5, s_pos.upper(), align='C')
    raw = BytesIO(pdf.output()); writer = PdfWriter(); writer.append_pages_from_reader(PdfReader(raw))
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 4. STABLE INTERFACE (NO-POPUP LOGIC)
# ==========================================
st.set_page_config(page_title="V5950 FINAL", layout="wide")

# ล็อกสถานะพิกัด
if 'st_lat' not in st.session_state: st.session_state.st_lat, st.session_state.st_lon = 13.75, 100.5
if 'pdf_data' not in st.session_state: st.session_state.pdf_data = None

# ฟังชันเรียก Dialog แบบเจาะจง
@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def open_archive_tool(sat_name, addr_dict):
    mode = st.radio("Time Mode", ["Live", "Predictive"], horizontal=True)
    t_sel = None
    if mode == "Predictive":
        c1, c2 = st.columns(2); d = c1.date_input("Date"); t = c2.time_input("Time")
        t_sel = datetime.combine(d, t).replace(tzinfo=timezone.utc)
    
    st.divider()
    s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
    s_pos = st.text_input("Position", "CHIEF COMMANDER")
    s_img = st.file_uploader("Seal (PNG)", type=['png'])
    
    if st.button("🚀 GENERATE PDF", use_container_width=True):
        m_data = run_calculation(sat_catalog[sat_name], st.session_state.st_lat, st.session_state.st_lon, t_sel)
        fid = f"REF-{random.randint(100, 999)}"; pwd = ''.join(random.choices(string.digits, k=6))
        st.session_state.pdf_data = build_pdf(sat_name, addr_dict, s_name, s_pos, s_img, fid, pwd, m_data)
        st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    
    if st.session_state.pdf_data:
        st.info(f"ID: {st.session_state.m_id} | PASS: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD", st.session_state.pdf_data, "report.pdf", use_container_width=True)

# --- SIDEBAR (Sliders Isolated) ---
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 STATION")
    f1 = st.text_input("Sub-District", "Phra Borom")
    f2 = st.text_input("District", "Phra Nakhon")
    f3 = st.text_input("Province", "Bangkok")
    f4 = st.text_input("Country", "Thailand")
    addr_dict = {"sub": f1, "dist": f2, "prov": f3, "cntr": f4}

    if st.button("🔍 UPDATE LOCATION", use_container_width=True):
        loc = geolocator.geocode(f"{f1}, {f2}, {f3}, {f4}")
        if loc: st.session_state.st_lat, st.session_state.st_lon = loc.latitude, loc.longitude

    st.divider()
    # Sliders ที่นี่จะ "นิ่ง" ไม่เด้งป๊อปอัพแน่นอน
    z1 = st.slider("Tactical Zoom", 1, 18, 12)
    z2 = st.slider("Global Zoom", 1, 10, 2)
    z3 = st.slider("Station Zoom", 1, 18, 15)
    
    # ปุ่มเดียวที่จะเปิดป๊อปอัพ
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.pdf_data = None # ล้างข้อมูลเก่า
        open_archive_tool(sat_name, addr_dict)

# --- DASHBOARD (Fragmented) ---
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="text-align:center; margin-bottom:20px;"><div style="display:inline-block; background:white; border:4px solid black; padding:5px 50px; border-radius:100px; color:black; font-size:40px; font-weight:bold;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div></div>''', unsafe_allow_html=True)
    m = run_calculation(sat_catalog[sat_name], st.session_state.st_lat, st.session_state.st_lon)
    
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, foot=0):
        fig = go.Figure()
        if foot > 0: fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=zm*15, color='rgba(0, 255, 0, 0.1)')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=14, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m['FOOTPRINT'])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1")
    with m_cols[2]: draw_map(st.session_state.st_lat, st.session_state.st_lon, z3, "S1")
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 8, 4)]))

dashboard()