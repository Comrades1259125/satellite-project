import streamlit as st  # บรรทัดที่ 1 ต้องเป็นอันนี้เท่านั้น!
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

# ==========================================
# 1. SETUP & SESSION STATE (ห้ามย้ายลำดับ)
# ==========================================
st.set_page_config(page_title="V5950 PRECISE COMMAND", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'addr_confirmed' not in st.session_state: st.session_state.addr_confirmed = False

@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try: return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

# ==========================================
# 2. CORE LOGIC FUNCTIONS
# ==========================================
def generate_strict_id():
    p1 = "".join(random.choices(string.digits, k=3))
    p2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=5))
    p3 = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
    return f"REF-{p1}-{p2}-{p3}"

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # 40 Telemetry Functions
    tele = {"TRK_LAT": f"{subpoint.latitude.degrees:.4f}", "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
            "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H"}
    prefixes = ["EPS", "ADC", "OBC", "TCS", "RCS", "PLD", "COM", "BUS"]
    for p in prefixes:
        for s in ["STAT", "VOLT", "CURR", "TEMP"]:
            if len(tele) < 40: tele[f"{p}_{s}"] = f"{random.uniform(10.0, 95.0):.2f}"

    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, 
            "RAW_TELE": tele, "TIME": t_input}

# ==========================================
# 3. PDF ENGINE
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(200); self.set_line_width(0.05)
        for i in range(1, 41): self.line(x + (i*w/40), y, x + (i*w/40), y+h)
        for i in range(1, 21): self.line(x, y + (i*h/20), x+w, y + (i*h/20))
        self.set_draw_color(0); self.set_line_width(0.4); self.rect(x, y, w, h)
        if data:
            min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 20); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", 'B', 7); pdf.cell(15, 8, f" {items[i+j][0]}:", 1)
                pdf.set_font("helvetica", '', 7); pdf.cell(32.25, 8, f"{items[i+j][1]}", 1)
        pdf.ln()
    pdf.add_page()
    pdf.draw_precision_graph(25, 30, 160, 65, "ORBITAL TRACK", m['TAIL_LAT'])
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 4. DIALOG & INTERFACE
# ==========================================
@st.dialog("📋 OFFICIAL ARCHIVE FINALIZATION")
def archive_dialog(sat_name, addr_data):
    if st.session_state.pdf_blob is None:
        s_name = st.text_input("AUTHORIZED BY", "DIRECTOR TRIN")
        s_pos = st.text_input("POSITION", "CHIEF COMMANDER")
        s_img = st.file_uploader("OFFICIAL SEAL (PNG)", type=['png'])
        if st.button("🚀 INITIATE GENERATION", use_container_width=True):
            fid, pwd = generate_strict_id(), ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name])
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.markdown(f'<div style="background:white; border:4px solid black; padding:30px; text-align:center; color:black;">ID: {st.session_state.m_id}<br><br><span style="font-size:30px; font-weight:900;">KEY: {st.session_state.m_pwd}</span></div>', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("CLOSE"): st.session_state.open_sys = False; st.rerun()

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    if sat_catalog:
        asset = st.selectbox("SELECT ASSET", list(sat_catalog.keys()))
        a1 = st.text_input("Sub-District", "Phra Borom")
        a2 = st.text_input("District", "Phra Nakhon")
        a3 = st.text_input("Province", "Bangkok")
        addr_data = {"sub": a1, "dist": a2, "prov": a3}
        if st.button("✅ CONFIRM ADDRESS", use_container_width=True): 
            st.session_state.addr_confirmed = True
        st.divider()
        # แถบซูมพร้อม Key ป้องกันป๊อปอัพเด้ง
        z1 = st.slider("Tactical Zoom", 1, 18, 12, key="fix_z1")
        z2 = st.slider("Global Zoom", 1, 10, 2, key="fix_z2")
        z3 = st.slider("Station Zoom", 1, 18, 15, key="fix_z3")
        if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
            if st.session_state.addr_confirmed: st.session_state.open_sys = True
            else: st.error("CONFIRM ADDRESS FIRST")
    else: st.error("DATABASE OFFLINE")

# เรียกใช้ป๊อปอัพเฉพาะตอนที่ open_sys เป็น True
if st.session_state.get('open_sys', False):
    archive_dialog(asset, addr_data)

# ==========================================
# 5. LIVE DASHBOARD (STABLE FRAGMENT)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard(sat_name):
    m = run_calculation(sat_catalog[sat_name])
    st.markdown(f'<div style="text-align:center;"><span style="font-size:50px; font-weight:900;">{datetime.now(timezone.utc).strftime("%H:%M:%S")} UTC</span></div>', unsafe_allow_html=True)
    
    cols = st.columns(3)
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=2, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", 
                                     layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], 
                                     center=dict(lat=lt, lon=ln), zoom=zm), 
                         margin=dict(l=0,r=0,t=0,b=0), height=400)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with cols[0]: draw_map(m['LAT'], m['LON'], z1, "m1", m["TAIL_LAT"], m["TAIL_LON"])
    with cols[1]: draw_map(m['LAT'], m['LON'], z2, "m2", m["TAIL_LAT"], m["TAIL_LON"])
    with cols[2]: draw_map(13.75, 100.5, z3, "m3", [], [])
    
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog:
    dashboard(asset)