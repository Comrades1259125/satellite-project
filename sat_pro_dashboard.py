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
# 2. PDF ENGINE (ระบบที่อยู่ 5 ช่อง + ลายเซ็น)
# ==========================================
def build_pdf(sat_name, addr_dict, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF(); pdf.add_page()
    pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, "OFFICIAL MISSION DATA REPORT", ln=True, align='C')
    pdf.set_font("Arial", '', 10); pdf.cell(0, 10, f"REPORT ID: {f_id} | ASSET: {sat_name}", ln=True, align='C')
    
    # ส่วนที่อยู่ 5 ช่องใน PDF
    pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, " GROUND STATION LOCATION DETAILS", ln=True, fill=True)
    pdf.set_font("Arial", '', 9)
    addr_text = f"Sub-district: {addr_dict['sub']} | District: {addr_dict['dist']} | Province: {addr_dict['prov']} | Zip: {addr_dict['zip']} | Country: {addr_dict['cntr']}"
    pdf.multi_cell(0, 8, addr_text, border=1)
    
    pdf.ln(5)
    # Telemetry Matrix 40 ช่อง
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, " TECHNICAL TELEMETRY MATRIX", ln=True, fill=True)
    pdf.set_font("Courier", '', 8)
    items = list(m['TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    # Signature Zone
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 240, 40, 20)
    pdf.line(140, 260, 195, 260)
    pdf.set_xy(140, 262); pdf.set_font("Arial", 'B', 10); pdf.cell(55, 5, s_name.upper(), align='C')

    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. SIDEBAR (ที่อยู่ 5 ช่องกลับมาแล้ว)
# ==========================================
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()))
    st.divider()
    
    st.subheader("📍 STATION LOCATION")
    a1 = st.text_input("1. Sub-District (ตำบล)", "That Choeng Chum")
    a2 = st.text_input("2. District (อำเภอ)", "Mueang Sakon Nakhon")
    a3 = st.text_input("3. Province (จังหวัด)", "Sakon Nakhon")
    a4 = st.text_input("4. Zip Code (รหัสไปรษณีย์)", "47000")
    a5 = st.text_input("5. Country (ประเทศ)", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "zip": a4, "cntr": a5}
    
    if st.button("✅ CONFIRM ALL LOCATION", use_container_width=True):
        st.session_state.st_coords = [17.16, 104.14] if "Sakon" in a3 else [13.75, 100.5]
        st.success("STATION ADDRESS LOCKED")

    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    if st.button("🧧 GENERATE REPORT", type="primary", use_container_width=True):
        st.session_state.pdf_ready = False
        st.session_state.open_sys = True

# ==========================================
# 4. DOWNLOAD DIALOG (FIXED NONE)
# ==========================================
if st.session_state.open_sys:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_dialog():
        if not st.session_state.pdf_ready:
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Position", "CHIEF COMMANDER")
            s_img = st.file_uploader("Upload Signature/Seal (PNG)", type=['png'])
            
            if st.button("🚀 INITIATE SYSTEM", use_container_width=True):
                # ล็อก ID/PASS ทันที ป้องกัน NONE
                st.session_state.m_id = f"REF-{random.randint(100, 999)}"
                st.session_state.m_pwd = ''.join(random.choices(string.digits, k=6))
                m_data = run_calculation(sat_catalog[sel_sat])
                st.session_state.pdf_blob = build_pdf(sel_sat, addr_data, s_name, s_pos, s_img, st.session_state.m_id, st.session_state.m_pwd, m_data)
                st.session_state.pdf_ready = True
                st.rerun()
        else:
            st.markdown(f'''
                <div style="background:white; border:5px solid red; padding:30px; text-align:center; color:black; border-radius:15px;">
                    <div style="font-size:16px; font-weight:bold;">ID:</div>
                    <div style="font-size:36px; font-weight:900; color:red;">{st.session_state.m_id}</div>
                    <div style="font-size:16px; font-weight:bold;">PASSKEY:</div>
                    <div style="font-size:52px; font-weight:900; letter-spacing:10px;">{st.session_state.m_pwd}</div>
                </div>
            ''', unsafe_allow_html=True)
            st.write("") 
            st.download_button("📥 DOWNLOAD ENCRYPTED PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
            if st.button("CLOSE"):
                st.session_state.open_sys = False
                st.session_state.pdf_ready = False
                st.rerun()
    archive_dialog()

# ==========================================
# 5. DASHBOARD DISPLAY (นาฬิกาขาวโบ๊ะ)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    # นาฬิกาแบบ image_42cd41.png
    st.markdown(f'''
        <div style="display:flex; justify-content:center; margin-bottom:30px;">
            <div style="background:white; border:6px solid black; padding:15px 100px; border-radius:150px; text-align:center; box-shadow: 0 10px 40px rgba(0,0,0,0.5);">
                <div style="color:black; font-size:75px; font-weight:900; font-family:monospace; line-height:1;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div>
                <div style="color:#444; font-size:14px; font-weight:bold; margin-top:5px;">STATION: {a1.upper()}, {a3.upper()}</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    m = run_calculation(sat_catalog[sel_sat])
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", m['TELE']['ALTITUDE'])
    c2.metric("VELOCITY", m['TELE']['VELOCITY'])
    c3.metric("CURRENT LAT", m['TELE']['LATITUDE'])

    # Maps
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, color='red'):
        fig = go.Figure(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=18, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T")
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G")
    with m_cols[2]: draw_map(st.session_state.st_coords[0], st.session_state.st_coords[1], z3, "S", "blue")

    st.table(pd.DataFrame([list(m["TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()