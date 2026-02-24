import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84

# ==========================================
# 1. CORE SYSTEM & STATE
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

def get_telemetry(sat_obj):
    t = ts.now(); g = sat_obj.at(t); sub = wgs84.subpoint(g)
    v = np.linalg.norm(g.velocity.km_per_s)
    tele = {"LATITUDE": f"{sub.latitude.degrees:.5f}°", "LONGITUDE": f"{sub.longitude.degrees:.5f}°",
            "ALTITUDE": f"{sub.elevation.km:.2f} KM", "VELOCITY": f"{v * 3600:.1f} KM/H"}
    for i in range(1, 37): tele[f"DATA_CH_{i:02d}"] = f"{random.uniform(10,99):.2f}"
    
    # ข้อมูลกราฟ (ประวัติ 10 จุด)
    history = [random.uniform(400, 450) for _ in range(20)]
    return {"LAT": sub.latitude.degrees, "LON": sub.longitude.degrees, "TELE": tele, "GRAPH": history}

# ==========================================
# 2. PDF ENGINE (2 PAGES: DATA + GRAPH/SIG)
# ==========================================
class MISSION_PDF(FPDF):
    def draw_graph(self, x, y, w, h, data):
        self.set_draw_color(0, 0, 0); self.rect(x, y, w, h)
        self.set_font("Arial", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, "ORBITAL STABILITY ANALYSIS")
        points = [(x + (i*(w/len(data))), (y+h) - ((v-min(data))/(max(data)-min(data)+1)*h)) for i,v in enumerate(data)]
        for i in range(len(points)-1): self.line(points[i][0], points[i][1], points[i+1][0], points[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = MISSION_PDF()
    # หน้า 1: ข้อมูลและตาราง
    pdf.add_page()
    pdf.set_font("Arial", 'B', 18); pdf.cell(0, 15, f"MISSION DATA: {sat_name}", ln=True, align='C')
    pdf.set_font("Arial", '', 10); pdf.cell(0, 8, f"ID: {f_id} | {addr['sub']}, {addr['prov']}", ln=True, align='C')
    pdf.ln(5)
    items = list(m['TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.5, 9, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    
    # หน้า 2: กราฟและลายเซ็น (ตามที่พี่สั่ง)
    pdf.add_page()
    pdf.draw_graph(20, 30, 170, 60, m['GRAPH'])
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 235, 40, 20)
    pdf.line(140, 255, 195, 255)
    pdf.set_xy(140, 257); pdf.set_font("Arial", 'B', 10); pdf.cell(55, 5, s_name.upper(), align='C')
    pdf.set_xy(140, 262); pdf.set_font("Arial", '', 8); pdf.cell(55, 5, s_pos.upper(), align='C')

    # เข้ารหัส
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. INTERFACE (SIDEBAR & DASHBOARD)
# ==========================================
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()))
    st.divider()
    a1 = st.text_input("Sub-District", "That Choeng Chum")
    a2 = st.text_input("District", "Mueang Sakon Nakhon")
    a3 = st.text_input("Province", "Sakon Nakhon")
    a4 = st.text_input("Zip Code", "47000")
    a5 = st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "zip": a4, "cntr": a5}
    
    if st.button("✅ CONFIRM & LOCK ADDRESS"):
        st.session_state.st_coords = [17.16, 104.14] if "Sakon" in a3 else [13.75, 100.5]

    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    if st.button("🧧 GENERATE MISSION ARCHIVE", type="primary", use_container_width=True):
        st.session_state.pdf_ready = False; st.session_state.open_sys = True

# ==========================================
# 4. DIALOG (ล็อกหน้าจอรหัสตาม image.png)
# ==========================================
if st.session_state.open_sys:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_dialog():
        if not st.session_state.pdf_ready:
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Position", "CHIEF COMMANDER")
            s_img = st.file_uploader("Upload Signature (PNG)", type=['png'])
            if st.button("🚀 INITIATE SECURE GENERATION", use_container_width=True):
                st.session_state.m_id = f"REF-{random.randint(100, 999)}-{datetime.now().strftime('%m%d')}"
                st.session_state.m_pwd = ''.join(random.choices(string.digits, k=6))
                m_data = get_telemetry(sat_catalog[sel_sat])
                st.session_state.pdf_blob = build_pdf(sel_sat, addr_data, s_name, s_pos, s_img, st.session_state.m_id, st.session_state.m_pwd, m_data)
                st.session_state.pdf_ready = True; st.rerun()
        else:
            # หน้ารหัสตามแบบ image.png
            st.markdown(f'''
                <div style="background:white; border:2px solid #333; padding:40px 20px; text-align:center; color:black; border-radius:15px; font-family:sans-serif;">
                    <div style="font-size:12px; font-weight:bold; color:#666; margin-bottom:10px;">DOCUMENT ARCHIVE ID</div>
                    <div style="font-size:32px; font-weight:900; color:#d9534f; margin-bottom:25px;">{st.session_state.m_id}</div>
                    <hr style="border:0; border-top:1px solid #eee; margin-bottom:25px;">
                    <div style="font-size:12px; font-weight:bold; color:#666; margin-bottom:10px;">ENCRYPTION KEY</div>
                    <div style="font-size:55px; font-weight:900; letter-spacing:10px; color:black;">{st.session_state.m_pwd}</div>
                </div>
            ''', unsafe_allow_html=True)
            st.write("")
            st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
            if st.button("RETURN", use_container_width=True):
                st.session_state.open_sys = False; st.session_state.pdf_ready = False; st.rerun()
    archive_dialog()

# ==========================================
# 5. LIVE DASHBOARD (นาฬิกาขาวมนตามรูป)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''
        <div style="display:flex; justify-content:center; margin-bottom:20px;">
            <div style="background:white; border:4px solid black; padding:10px 100px; border-radius:100px; text-align:center;">
                <div style="color:black; font-size:65px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div>
                <div style="color:#666; font-size:12px; font-weight:bold;">LOCATION: {a3.upper()}</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    m = get_telemetry(sat_catalog[sel_sat])
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", m['TELE']['ALTITUDE'])
    c2.metric("VELOCITY", m['TELE']['VELOCITY'])
    c3.metric("POSITION", m['TELE']['LATITUDE'])

    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, color='red'):
        fig = go.Figure(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=18, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380)
        st.plotly_chart(fig, use_container_width=True, key=k)
    
    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "t1")
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "t2")
    with m_cols[2]: draw_map(st.session_state.st_coords[0], st.session_state.st_coords[1], z3, "t3", "blue")

    st.table(pd.DataFrame([list(m["TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()