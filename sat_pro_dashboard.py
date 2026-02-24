import streamlit as st  # บรรทัดที่ 1 ห้ามขยับ!
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
# 1. INITIAL SETUP & STATE
# ==========================================
st.set_page_config(page_title="V5950 SAT-COMMAND", layout="wide")

# ป้องกัน Error กรณีเปิดแอปครั้งแรก
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
# 2. CALCULATION ENGINE
# ==========================================
def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # 40 Functions
    tele = {"TRK_LAT": f"{subpoint.latitude.degrees:.4f}", "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
            "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H"}
    for p in ["EPS", "ADC", "OBC", "TCS", "RCS", "PLD", "COM", "BUS"]:
        for s in ["STAT", "VOLT", "CURR", "TEMP"]:
            if len(tele) < 40: tele[f"{p}_{s}"] = f"{random.uniform(10, 99):.2f}"

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
# 3. PDF & QR GENERATOR
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_graph(self, x, y, w, h, title, data):
        self.set_fill_color(250); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 8); self.set_xy(x, y-4); self.cell(w, 4, title)
        if data:
            min_d, max_d = min(data), max(data); r = (max_d - min_d) if max_d != min_d else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_d)/r*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_line_width(0.5); self.set_draw_color(200, 0, 0)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16); pdf.cell(0, 10, f"MISSION ARCHIVE: {f_id}", ln=True, align='C')
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", 'B', 6); pdf.cell(12, 7, f"{items[i+j][0]}:", 1)
                pdf.set_font("helvetica", '', 6); pdf.cell(35, 7, f"{items[i+j][1]}", 1)
        pdf.ln()
    pdf.draw_graph(20, 100, 170, 50, "LATITUDE HISTORY", m['TAIL_LAT'])
    writer = PdfWriter(); raw = BytesIO(pdf.output()); reader = PdfReader(raw)
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 4. DIALOG & SIDEBAR (THE FIX)
# ==========================================
@st.dialog("📋 OFFICIAL FINALIZATION")
def archive_dialog(asset, addr):
    if st.session_state.pdf_blob is None:
        s_name = st.text_input("SIGNER", "DIRECTOR TRIN")
        pwd = st.text_input("SET PASSWORD", "123456", type="password")
        if st.button("🚀 GENERATE"):
            fid = f"REF-{random.randint(100,999)}"
            m_data = run_calculation(sat_catalog[asset])
            st.session_state.pdf_blob = build_pdf(asset, addr, s_name, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.success(f"ID: {st.session_state.m_id} | KEY: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD", st.session_state.pdf_blob, "report.pdf")
        if st.button("CLOSE"): st.session_state.open_sys = False; st.rerun()

# --- SIDEBAR (เริ่มบรรทัดที่เน้นแก้ NameError) ---
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    asset = st.selectbox("SELECT ASSET", list(sat_catalog.keys()) if sat_catalog else ["NONE"])
    a1 = st.text_input("Address", "Bangkok")
    if st.button("✅ CONFIRM"): st.session_state.addr_confirmed = True
    st.divider()
    # Key สำคัญมาก กันป๊อปอัพเด้ง!
    z1 = st.slider("Tactical Zoom", 1, 18, 12, key="fix_z1")
    z2 = st.slider("Global Zoom", 1, 10, 2, key="fix_z2")
    z3 = st.slider("Station Zoom", 1, 18, 15, key="fix_z3")
    if st.button("🧧 EXECUTE REPORT", type="primary"):
        if st.session_state.addr_confirmed: st.session_state.open_sys = True
        else: st.error("CONFIRM ADDRESS FIRST")

# เรียก Dialog ชั้นนอกสุด
if st.session_state.get('open_sys', False):
    archive_dialog(asset, a1)

# ==========================================
# 5. DASHBOARD (CENTERED MAP)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard(asset_name):
    m = run_calculation(sat_catalog[asset_name])
    st.markdown(f"<h1 style='text-align:center;'>{datetime.now().strftime('%H:%M:%S')}</h1>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    def map_func(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", 
            layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
            center=dict(lat=lt, lon=ln), zoom=zm), # ล็อกกลางจอ!
            margin=dict(l=0,r=0,t=0,b=0), height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with c1: map_func(m['LAT'], m['LON'], z1, "m1", m["TAIL_LAT"], m["TAIL_LON"])
    with c2: map_func(m['LAT'], m['LON'], z2, "m2", m["TAIL_LAT"], m["TAIL_LON"])
    with c3: map_func(13.75, 100.5, z3, "m3", [], [])
    
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog:
    dashboard(asset)