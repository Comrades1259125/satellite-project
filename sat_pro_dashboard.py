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

# ==========================================
# 1. INITIALIZE SESSION STATE (ป้องกันป๊อปอัพเด้งเอง)
# ==========================================
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'm_id' not in st.session_state: st.session_state.m_id = "WAITING..."
if 'm_pwd' not in st.session_state: st.session_state.m_pwd = "******"
if 'station_coords' not in st.session_state: st.session_state.station_coords = [17.16, 104.14]

# ==========================================
# 2. CORE DATA ENGINE
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.5f}°", "TRK_LON": f"{subpoint.longitude.degrees:.5f}°",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.0, 32.0):.2f} V", "EPS_SOLAR_A": f"{random.uniform(5.5, 8.2):.2f} A",
        "NORAD_ID": "25544", "MISSION": "NOMINAL"
    }
    for i in range(1, 33): tele[f"PARAM_{i+8}"] = "STABLE"
    
    # ดึงพิกัดย้อนหลังสำหรับทำเส้น Tail (นิ่งขึ้น)
    lats, lons = [], []
    for i in range(0, 51, 5):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT": subpoint.elevation.km, "VEL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TELE": tele}

# ==========================================
# 3. PDF ENGINE (กู้คืนระบบลายเซ็น)
# ==========================================
def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 18); pdf.cell(0, 15, f"OFFICIAL MISSION DATA REPORT: {sat_name}", ln=True, align='C')
    pdf.set_font("Arial", '', 10); pdf.cell(0, 10, f"ID: {f_id} | MODE: Live Now", ln=True, align='C')
    pdf.ln(5)
    
    # Ground Station Info
    pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, " GROUND STATION IDENTIFICATION", ln=True, fill=True)
    pdf.set_font("Arial", '', 10); pdf.cell(0, 10, f" Location: {addr}", ln=True)
    
    # Telemetry Matrix (40 ช่อง)
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, " TECHNICAL TELEMETRY MATRIX", ln=True, fill=True)
    pdf.set_font("Courier", '', 7)
    items = list(m['TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    
    # Signature Zone (กู้คืนระบบรูปภาพ)
    if s_img:
        pdf.image(BytesIO(s_img.getvalue()), 150, 240, 35, 20)
    pdf.line(140, 265, 195, 265)
    pdf.set_xy(140, 267); pdf.set_font("Arial", 'B', 10); pdf.cell(55, 5, s_name.upper(), align='C')

    # Encryption
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 4. DASHBOARD UI
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    st.divider()
    sub_d = st.text_input("Sub-District", "That Choeng Chum")
    dist = st.text_input("District", "Mueang Sakon Nakhon")
    prov = st.text_input("Province", "Sakon Nakhon")
    full_addr = f"{sub_d}, {dist}, {prov}, Thailand"
    
    if st.button("✅ CONFIRM LOCATION"):
        st.session_state.station_coords = [17.16, 104.14] if "Sakon" in prov else [13.75, 100.5]
        st.success("STATION LOCKED")

    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    st.divider()
    if st.button("🧧 GENERATE REPORT", type="primary", use_container_width=True):
        st.session_state.open_sys = True # กดแล้วถึงจะเปิด

# --- Dialog กู้คืนระบบรหัสผ่านและดาวน์โหลด ---
if st.session_state.open_sys:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_dialog():
        if st.session_state.pdf_blob is None:
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Position", "CHIEF COMMANDER")
            s_img = st.file_uploader("Upload Signature/Seal (PNG)", type=['png'])
            
            if st.button("🚀 INITIATE DOWNLOAD PROCESS", use_container_width=True):
                st.session_state.m_id = f"REF-{random.randint(100, 999)}"
                st.session_state.m_pwd = ''.join(random.choices(string.digits, k=6))
                m_data = run_calculation(sat_catalog[sat_name])
                st.session_state.pdf_blob = build_pdf(sat_name, full_addr, s_name, s_pos, s_img, st.session_state.m_id, st.session_state.m_pwd, m_data)
                st.rerun()
        else:
            # หน้าจอ ID/PASS ตามรูปที่พี่ต้องการ
            st.markdown(f'''
                <div style="background:white; border:4px solid red; padding:30px; text-align:center; color:black; border-radius:10px;">
                    <div style="font-size:14px; font-weight:bold; color:#666;">ID:</div>
                    <div style="font-size:32px; font-weight:900; color:red; margin-bottom:10px;">{st.session_state.m_id}</div>
                    <div style="font-size:14px; font-weight:bold; color:#666;">PASSKEY:</div>
                    <div style="font-size:48px; font-weight:900; letter-spacing:8px;">{st.session_state.m_pwd}</div>
                </div>
            ''', unsafe_allow_html=True)
            st.ln(2)
            st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
            if st.button("CLOSE"):
                st.session_state.pdf_blob = None; st.session_state.open_sys = False; st.rerun()
    archive_dialog()

# ==========================================
# 5. LIVE DASHBOARD (นาฬิกาขาวตามรูป)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    # นาฬิกาแบบในรูป (ขาวนวล ขอบดำ)
    st.markdown(f'''
        <div style="display:flex; justify-content:center; margin-bottom:20px;">
            <div style="background:white; border:4px solid black; padding:10px 80px; border-radius:100px; text-align:center;">
                <div style="color:black; font-size:65px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div>
                <div style="color:#666; font-size:12px; font-weight:bold;">LOCATION: {prov}</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    m = run_calculation(sat_catalog[sat_name])
    
    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT']:.2f} KM")
    c2.metric("VELOCITY", f"{m['VEL']:.2f} KM/H")
    c3.metric("POSITION", f"LAT: {m['LAT']:.5f}°")

    # แผนที่นิ่ง (ใช้พิกัดจริง)
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, tl, tn, color='red'):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=f"{k}_{lt}")

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(st.session_state.station_coords[0], st.session_state.station_coords[1], z3, "S", [], [], 'blue')

    # ตาราง 40 ช่อง (กู้คืนรูปแบบเดิม)
    st.table(pd.DataFrame([list(m["TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()