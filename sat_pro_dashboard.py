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
# 1. SETUP & STATE MANAGEMENT
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

# ป้องกันค่าหายและป้องกันป๊อปอัพเด้งเอง
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_ready' not in st.session_state: st.session_state.pdf_ready = False
if 'm_id' not in st.session_state: st.session_state.m_id = ""
if 'm_pwd' not in st.session_state: st.session_state.m_pwd = ""
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'st_coords' not in st.session_state: st.session_state.st_coords = [17.16, 104.14]

@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj):
    t = ts.now(); geocentric = sat_obj.at(t); subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    tele = {"LATITUDE": f"{subpoint.latitude.degrees:.5f}°", "LONGITUDE": f"{subpoint.longitude.degrees:.5f}°",
            "ALTITUDE": f"{subpoint.elevation.km:.2f} KM", "VELOCITY": f"{v_km_s * 3600:.1f} KM/H"}
    for i in range(1, 37): tele[f"PARAM_{i}"] = "NOMINAL"
    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees, "TELE": tele}

# ==========================================
# 2. PDF ENGINE (ระบบลายเซ็นและเข้ารหัส)
# ==========================================
def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF(); pdf.add_page()
    pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, "OFFICIAL MISSION DATA REPORT", ln=True, align='C')
    pdf.set_font("Arial", '', 12); pdf.cell(0, 10, f"ASSET: {sat_name} | ID: {f_id}", ln=True, align='C')
    pdf.ln(5)
    # Ground Station Matrix
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, " TELEMETRY DATA MATRIX", ln=True, fill=True)
    pdf.set_font("Courier", '', 8)
    items = list(m['TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    # Signature
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 245, 40, 20)
    pdf.line(140, 265, 195, 265)
    pdf.set_xy(140, 267); pdf.set_font("Arial", 'B', 10); pdf.cell(55, 5, s_name.upper(), align='C')
    # Save & Encrypt
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. SIDEBAR & CONTROLS
# ==========================================
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()))
    st.divider()
    sub_d = st.text_input("Sub-District", "That Choeng Chum")
    prov = st.text_input("Province", "Sakon Nakhon")
    if st.button("✅ CONFIRM LOCATION"):
        st.session_state.st_coords = [17.16, 104.14] if "Sakon" in prov else [13.75, 100.5]
    
    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    if st.button("🧧 GENERATE REPORT", type="primary", use_container_width=True):
        st.session_state.pdf_ready = False # Reset ก่อนสร้างใหม่
        st.session_state.open_sys = True

# ==========================================
# 4. DOWNLOAD DIALOG (FIXED NONE & ERROR)
# ==========================================
if st.session_state.open_sys:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_dialog():
        if not st.session_state.pdf_ready:
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Position", "CHIEF COMMANDER")
            s_img = st.file_uploader("Upload Signature/Seal (PNG)", type=['png'])
            
            if st.button("🚀 INITIATE SYSTEM", use_container_width=True):
                # ล็อกค่าเข้า State ทันที ป้องกัน None
                st.session_state.m_id = f"REF-{random.randint(100, 999)}"
                st.session_state.m_pwd = ''.join(random.choices(string.digits, k=6))
                m_data = run_calculation(sat_catalog[sel_sat])
                st.session_state.pdf_blob = build_pdf(sel_sat, f"{sub_d}, {prov}", s_name, s_pos, s_img, st.session_state.m_id, st.session_state.m_pwd, m_data)
                st.session_state.pdf_ready = True
                st.rerun()
        else:
            # หน้ารหัสผ่าน (Style ขาว-แดง ตามรูปพี่เป๊ะ)
            st.markdown(f'''
                <div style="background:white; border:5px solid red; padding:30px; text-align:center; color:black; border-radius:15px;">
                    <div style="font-size:16px; font-weight:bold; color:black;">ID:</div>
                    <div style="font-size:36px; font-weight:900; color:red; margin-bottom:15px;">{st.session_state.m_id}</div>
                    <div style="font-size:16px; font-weight:bold; color:black;">PASSKEY:</div>
                    <div style="font-size:52px; font-weight:900; letter-spacing:10px; color:black;">{st.session_state.m_pwd}</div>
                </div>
            ''', unsafe_allow_html=True)
            st.write("") # แทน st.ln(2) ที่ทำให้เกิด Error
            st.download_button("📥 DOWNLOAD ENCRYPTED PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
            if st.button("CLOSE & RESET"):
                st.session_state.open_sys = False
                st.session_state.pdf_ready = False
                st.rerun()
    archive_dialog()

# ==========================================
# 5. DASHBOARD DISPLAY (นาฬิกาขาวนวล)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    # นาฬิกาแบบ image_42cd41.png
    st.markdown(f'''
        <div style="display:flex; justify-content:center; margin-bottom:30px;">
            <div style="background:white; border:6px solid black; padding:15px 100px; border-radius:150px; text-align:center; box-shadow: 0 10px 40px rgba(0,0,0,0.5);">
                <div style="color:black; font-size:75px; font-weight:900; font-family:monospace; line-height:1;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div>
                <div style="color:#444; font-size:14px; font-weight:bold; margin-top:5px;">LOCATION: {prov.upper()}</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    m = run_calculation(sat_catalog[sel_sat])
    
    # Metrics (Style image_43a3ba.png)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div style='border-left:5px solid #00ff00; padding-left:10px;'>ALTITUDE<br><h2 style='margin:0;'>{m['TELE']['ALTITUDE']}</h2></div>", unsafe_allow_html=True)
    c2.markdown(f"<div style='border-left:5px solid #ffff00; padding-left:10px;'>VELOCITY<br><h2 style='margin:0;'>{m['TELE']['VELOCITY']}</h2></div>", unsafe_allow_html=True)
    c3.markdown(f"<div style='border-left:5px solid #00aaff; padding-left:10px;'>POSITION<br><h2 style='margin:0;'>{m['TELE']['LATITUDE']}</h2></div>", unsafe_allow_html=True)

    # Maps
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, color='red'):
        fig = go.Figure(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=18, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "tactical")
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "global")
    with m_cols[2]: draw_map(st.session_state.st_coords[0], st.session_state.st_coords[1], z3, "station", "blue")

    st.table(pd.DataFrame([list(m["TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()