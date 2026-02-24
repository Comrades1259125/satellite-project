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
# 1. CORE DATA ENGINE (RESTORED & OPTIMIZED)
# ==========================================
@st.cache_resource
def init_satellite_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        satellites = load.tle_file(url)
        return {sat.name: sat for sat in satellites}
    except Exception as e:
        st.error(f"System Link Failure: {e}")
        return {}

sat_catalog = init_satellite_system()
ts = load.timescale()

def run_orbital_mechanics(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # Restored 40-Parameter Telemetry
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:,.2f} KM/H",
        "EPS_STAT": "NOMINAL",
        "EPS_V_BUS": f"{random.uniform(28.0, 32.0):.2f} V",
        "TCS_TEMP": f"{random.uniform(22, 28):.2f} C",
        "OBC_LOAD": f"{random.randint(20, 45)} %",
        "COM_SIGNAL": f"{random.uniform(-105, -90):.2f} dBm",
        "MISSION_PH": "PHASE-04",
        "SYS_LOCK": "AES-256",
        "ANT_POS": "DEPLOYED"
    }
    for i in range(28):
        tele[f"SENSOR_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # Trajectory Calculation (Past 100 mins)
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, 
        "RAW_TELE": tele
    }

# ==========================================
# 2. HD PDF & QR ARCHIVE (RESTORED)
# ==========================================
def generate_secure_qr(data):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    buf = BytesIO(); img.save(buf, format="PNG"); return buf

class ENGINEERING_PDF(FPDF):
    def draw_graph(self, x, y, w, h, title, data, color):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.5); self.rect(x, y, w, h)
        self.set_font("Helvetica", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 24); pdf.cell(0, 15, "MISSION ARCHIVE REPORT", ln=True, align='C')
    pdf.set_font("Helvetica", 'B', 12); pdf.cell(0, 10, f"REF ID: {f_id}", ln=True, align='C')
    pdf.set_font("Helvetica", '', 9); pdf.cell(0, 5, f"STATION: {addr.upper()}", ln=True, align='C')
    pdf.ln(10)
    
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("Helvetica", '', 7)
                pdf.cell(47.25, 8, f" {items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    pdf.add_page()
    pdf.draw_graph(20, 30, 170, 70, "ORBITAL TRAJECTORY (LAT)", m['TAIL_LAT'], (0, 80, 180))
    pdf.draw_graph(20, 115, 80, 50, "VELOCITY (KM/H)", m['TAIL_VEL'], (180, 100, 0))
    pdf.draw_graph(110, 115, 80, 50, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 60))
    
    qr_buf = generate_secure_qr(f_id)
    pdf.image(qr_buf, 20, 190, 40, 40)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 200, 30, 22)
    pdf.set_xy(110, 225); pdf.set_font("Helvetica", 'B', 12); pdf.cell(80, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("Helvetica", 'I', 10); pdf.cell(80, 5, s_pos.upper(), align='C')

    raw_out = BytesIO(pdf.output()); reader = PdfReader(raw_out); writer = PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (RESTORED TRIPLE ZOOM)
# ==========================================
st.set_page_config(page_title="V6.0 ULTIMATE", layout="wide")

if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'open_sys' not in st.session_state: st.session_state.open_sys = False

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    if sat_catalog:
        sel_sat = st.selectbox("SELECT ASSET", list(sat_catalog.keys()))
        sat_obj = sat_catalog[sel_sat]
    
    st.subheader("📍 STATION CONFIG")
    st_name = st.text_input("Station Name", "BANGKOK-01")
    
    st.divider()
    st.subheader("🔍 TRIPLE ZOOM CONTROL")
    z1 = st.slider("Tactical (Local)", 1, 18, 12)
    z2 = st.slider("Global (Orbit)", 1, 10, 2)
    z3 = st.slider("Station (Ground)", 1, 18, 15)
    
    if st.button("EXECUTE ARCHIVE", use_container_width=True, type="primary"):
        st.session_state.open_sys = True

@st.dialog("📋 ARCHIVE FINALIZATION")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Title", "CHIEF COMMANDER")
        s_img = st.file_uploader("Digital Seal (PNG)", type=['png'])
        if st.button("INITIATE ENCRYPTION"):
            fid = f"SEC-{random.randint(100,999)}"
            pwd = "123456" # Restored Simple Password
            m_data = run_orbital_mechanics(sat_obj)
            st.session_state.pdf_blob = build_archive(sel_sat, st_name, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id = fid; st.rerun()
    else:
        st.success(f"ARCHIVE READY: {st.session_state.m_id}")
        st.download_button("DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf")
        if st.button("RETURN"): st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.open_sys: archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    # Real-time Header
    st.markdown(f'''<div style="text-align:center; background:white; border:5px solid black; padding:10px; border-radius:100px; margin-bottom:20px;">
                <span style="color:black; font-size:50px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")} UTC</span></div>''', unsafe_allow_html=True)
    
    m = run_orbital_mechanics(sat_obj)
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT_VAL']:,.2f} KM")
    c2.metric("VELOCITY", f"{m['VEL_VAL']:,.0f} KM/H")
    c3.metric("COORDINATES", m["COORD"])
    
    # RESTORED TRIPLE MAP LAYOUT
    st.subheader("🌍 GEOSPATIAL COMMAND (TRIPLE VIEW)")
    m_cols = st.columns(3)
    
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "TACTICAL", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "GLOBAL", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(13.75, 100.5, z3, "STATION", [], []) # Fixed Ground Station

    st.subheader("📊 TELEMETRY ARCHIVE (RESTORED 40 PARAMS)")
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog: dashboard()