import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84

# ==========================================
# 1. SYSTEM CONFIG & SESSION STATE
# ==========================================
st.set_page_config(page_title="V5950 PRECISE COMMAND", layout="wide")

# สร้างสวิตช์ควบคุมป๊อปอัพแยกจาก Slider
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'addr_confirmed' not in st.session_state: st.session_state.addr_confirmed = False

@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try:
        data = load.tle_file(url)
        return {sat.name: sat for sat in data}
    except:
        return {}

sat_catalog = init_system()
ts = load.timescale()

# ==========================================
# 2. CALCULATION ENGINE (40 PARAMS)
# ==========================================
def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # Telemetry Data (40 ฟังก์ชันห้ามหาย)
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H"
    }
    prefixes = ["EPS", "ADC", "OBC", "TCS", "RCS", "PLD", "COM", "BUS"]
    for p in prefixes:
        for s in ["STAT", "VOLT", "CURR", "TEMP"]:
            if len(tele) < 40:
                tele[f"{p}_{s}"] = f"{random.uniform(10.0, 95.0):.2f}"

    # Historical Trail (100 mins)
    lats, lons = [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        ps = wgs84.subpoint(sat_obj.at(pt))
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "TAIL_LAT": lats, "TAIL_LON": lons, "RAW_TELE": tele}

# ==========================================
# 3. PDF REPORT ENGINE
# ==========================================
def build_pdf(sat_name, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.cell(0, 10, f"SATELLITE MISSION REPORT: {f_id}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("helvetica", '', 8)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 2):
        pdf.cell(45, 8, f"{items[i][0]}: {items[i][1]}", 1)
        if i+1 < 40:
            pdf.cell(45, 8, f"{items[i+1][0]}: {items[i+1][1]}", 1)
        pdf.ln()
    writer = PdfWriter(); raw = BytesIO(pdf.output()); reader = PdfReader(raw)
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 4. DIALOG CONTROL (FIXED POPUP ISSUE)
# ==========================================
@st.dialog("📋 OFFICIAL ARCHIVE FINALIZATION")
def archive_dialog(asset):
    if st.session_state.pdf_blob is None:
        pwd = st.text_input("SET REPORT PASSWORD", "123456", type="password")
        if st.button("🚀 INITIATE GENERATION", use_container_width=True):
            fid = f"REF-{random.randint(100,999)}"
            m_data = run_calculation(sat_catalog[asset])
            st.session_state.pdf_blob = build_pdf(asset, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd
            st.rerun()
    else:
        st.success(f"ID: {st.session_state.m_id} | KEY: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, "report.pdf", use_container_width=True)
        if st.button("CLOSE"):
            st.session_state.open_sys = False
            st.rerun()

# --- SIDEBAR CONTROL ---
with st.sidebar:
    st.header("🛰️ SAT-CONTROL")
    if sat_catalog:
        asset = st.selectbox("SELECT ASSET", list(sat_catalog.keys()))
        if st.button("✅ CONFIRM STATION"): 
            st.session_state.addr_confirmed = True
        
        st.divider()
        # Slider มี Key เพื่อแยก State ออกจากระบบอื่นเด็ดขาด
        z1 = st.slider("Tactical Zoom", 1, 18, 12, key="fix_z1")
        z2 = st.slider("Global Zoom", 1, 10, 2, key="fix_z2")
        z3 = st.slider("Station Zoom", 1, 18, 15, key="fix_z3")
        
        if st.button("🧧 EXECUTE REPORT", type="primary", use_container_width=True):
            if st.session_state.addr_confirmed:
                st.session_state.open_sys = True # สั่งเปิดป๊อปอัพ
            else:
                st.error("CONFIRM ADDRESS FIRST")

# ดักเรียก Dialog ไว้นอก Fragment เพื่อป้องกันการเด้งเวลาเลื่อนสไลเดอร์
if st.session_state.get('open_sys', False):
    archive_dialog(asset)

# ==========================================
# 5. DASHBOARD (CENTERED MAPS)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard(asset_name):
    m = run_calculation(sat_catalog[asset_name])
    st.markdown(f'''<div style="text-align:center; border:3px solid black; padding:10px; border-radius:15px; background:white;">
                <span style="font-size:40px; font-weight:900; color:black;">{datetime.now().strftime("%H:%M:%S")} UTC</span>
                </div>''', unsafe_allow_html=True)

    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl:
            fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=2, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        
        fig.update_layout(
            mapbox=dict(
                style="white-bg",
                layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
                center=dict(lat=lt, lon=ln), # แก้ไข: ล็อกพิกัด Center ให้แผนที่ตามหมุดตลอดเวลา
                zoom=zm
            ),
            margin=dict(l=0, r=0, t=0, b=0), height=400, showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True, key=k)

    c1, c2, c3 = st.columns(3)
    with c1: draw_map(m['LAT'], m['LON'], z1, "m1", m["TAIL_LAT"], m["TAIL_LON"])
    with c2: draw_map(m['LAT'], m['LON'], z2, "m2", m["TAIL_LAT"], m["TAIL_LON"])
    with c3: draw_map(13.75, 100.5, z3, "m3", [], []) # ล็อกพิกัดสถานีภาคพื้นดิน

    st.subheader("📊 TELEMETRY STATUS (40 PARAMS)")
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog:
    dashboard(asset)