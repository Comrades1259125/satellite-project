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
# 1. CORE DATA ENGINE (TLE & PHYSICS)
# ==========================================
@st.cache_resource
def init_system():
    # ดึงข้อมูลดาวเทียมแบบ Real-time จาก Celestrak
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try:
        satellites = load.tle_file(url)
        return {sat.name: sat for sat in satellites}
    except:
        return {}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # ระบบ Telemetry 40 พารามิเตอร์ (Simulation)
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.0, 32.0):.2f} V",
        "EPS_SOLAR_A": f"{random.uniform(5.5, 8.2):.2f} A",
        "ADC_GYRO_X": f"{random.uniform(-0.01, 0.01):.4f}",
        "OBC_STATUS": "ACTIVE",
        "COM_MODE": "ENCRYPTED",
        "SYS_LOCK": "AES-256",
        "MISSION_PH": "PHASE-04"
    }
    # เติมให้ครบ 40 ตัวสำหรับตาราง
    for i in range(29):
        tele[f"PARAM_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # คำนวณเส้นทางย้อนหลัง 100 นาที (Trail)
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees)
        lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km)
        vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, 
        "RAW_TELE": tele
    }

# ==========================================
# 2. PDF & QR GENERATION ENGINE
# ==========================================
def generate_verified_qr(data_text):
    qr = qrcode.QRCode(border=2)
    qr.add_data(data_text); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    buf = BytesIO(); img.save(buf, format="PNG"); return buf

class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.4); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 20); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", '', 10); pdf.cell(0, 8, f"ASSET: {sat_name} | ID: {f_id}", ln=True, align='C')
    
    # Telemetry Table
    pdf.ln(5); pdf.set_font("helvetica", '', 8)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < 40: pdf.cell(47, 7, f"{items[i+j][0]}: {items[i+j][1]}", 1)
        pdf.ln()
    
    # Graphs Page
    pdf.add_page()
    pdf.draw_precision_graph(20, 30, 170, 60, "ORBITAL LATITUDE TRACK", m['TAIL_LAT'])
    pdf.draw_precision_graph(20, 110, 80, 50, "VELOCITY (KM/H)", m['TAIL_VEL'], (180, 100, 0))
    pdf.draw_precision_graph(110, 110, 80, 50, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 60))
    
    # QR & Signature
    qr_buf = generate_verified_qr(f_id)
    pdf.image(qr_buf, 20, 190, 40, 40)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 140, 190, 30, 20)
    pdf.set_xy(110, 215); pdf.set_font("helvetica", 'B', 12); pdf.cell(80, 7, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("helvetica", 'I', 10); pdf.cell(80, 5, s_pos.upper(), align='C')
    
    # Encryption
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (STREAMLIT DASHBOARD)
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

# Mobile Friendly CSS
st.markdown("<style>.stMetric { background: #f0f2f6; padding: 10px; border-radius: 10px; border: 1px solid #ccc; }</style>", unsafe_allow_html=True)

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ COMMAND CENTER")
    sat_name = st.selectbox("SELECT ASSET", list(sat_catalog.keys()) if sat_catalog else ["Loading..."])
    st.subheader("📍 STATION INFO")
    a1 = st.text_input("Sub-District", "Phra Nakhon")
    a2 = st.text_input("Province", "Bangkok")
    addr_data = {"sub": a1, "prov": a2}
    
    z1 = st.slider("Tactical Zoom", 1, 18, 12, key="z1")
    z2 = st.slider("Global View", 1, 10, 2, key="z2")
    z3 = st.slider("Station View", 1, 18, 15, key="z3")
    
    if st.button("🧧 EXECUTE REPORT", type="primary", use_container_width=True):
        st.session_state.open_sys = True

@st.dialog("📋 ARCHIVE FINALIZATION")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Upload Digital Seal (PNG)", type=['png'])
        pwd = st.text_input("Set PDF Password (6 Digits)", "123456", type="password")
        if st.button("🚀 GENERATE SECURE ARCHIVE", use_container_width=True):
            fid = f"REF-{random.randint(100,999)}"
            m_data = run_calculation(sat_catalog[sat_name])
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd
            st.rerun()
    else:
        st.success(f"ARCHIVE READY | ID: {st.session_state.m_id}")
        st.info(f"PDF PASSWORD: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"REPORT_{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("RETURN TO DASHBOARD"):
            st.session_state.pdf_blob = None
            st.session_state.open_sys = False
            st.rerun()

if st.session_state.open_sys: archive_dialog()

# --- MAIN DASHBOARD ---
@st.fragment(run_every=1.0)
def dashboard():
    m = run_calculation(sat_catalog[sat_name])
    
    # 1. Clock & Metrics
    st.markdown(f"<h1 style='text-align:center; background:white; border:4px solid black; padding:10px;'>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</h1>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT_VAL']:.2f} KM")
    c2.metric("VELOCITY", f"{m['VEL_VAL']:.2f} KM/H")
    c3.metric("COORD", m["COORD"])
    
    # 2. Triple Maps
    st.subheader("🌍 GEOSPATIAL COMMAND")
    m_cols = st.columns(3)
    
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        fig.update_layout(
            mapbox=dict(style="white-bg", 
                        layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
                        center=dict(lat=lt, lon=ln), zoom=zm),
            margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], [])

    # 3. Telemetry Table
    st.subheader("📊 SYSTEM TELEMETRY (40 PARAMS)")
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog:
    dashboard()