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
from PIL import Image, ImageDraw

# ==========================================
# 1. CORE ENGINE (SINGLE SOURCE OF TRUTH)
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

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
    
    # 40 Functions (Cleaned)
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
    }
    # Subsystem Parameters
    sub = ["EPS", "ADC", "OBC", "TCS", "RCS", "PLD", "COM", "BUS"]
    for p in sub:
        for s in ["STAT", "VOLT", "CURR", "TEMP"]:
            if len(tele) < 40: tele[f"{p}_{s}"] = f"{random.uniform(10, 95):.2f}"

    # Trail Calculation
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, 
            "RAW_TELE": tele, "TIME": t_input}

# ==========================================
# 2. INTERFACE & LOGIC (FIXED POPUP)
# ==========================================
st.set_page_config(page_title="V5950 PRECISE", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'addr_confirmed' not in st.session_state: st.session_state.addr_confirmed = False

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 STATION LOCATION")
    a1 = st.text_input("Sub-District", "Phra Borom")
    a2 = st.text_input("District", "Phra Nakhon")
    a3 = st.text_input("Province", "Bangkok")
    a4 = st.text_input("Country", "Thailand")
    
    if st.button("✅ CONFIRM ADDRESS", use_container_width=True):
        st.session_state.addr_confirmed = True
        st.success("Address Locked")
        
    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        if st.session_state.addr_confirmed:
            st.session_state.pdf_blob = None
            st.session_state.open_sys = True
            st.rerun()
        else:
            st.error("Please confirm address first!")

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    # ล็อคไม่ให้ทำงานถ้าสถานะเป็น False
    if not st.session_state.open_sys:
        return

    if st.session_state.pdf_blob is None:
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        
        mode = st.radio("Time Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            t_sel = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
            
        if st.button("🚀 INITIATE", use_container_width=True):
            fid = generate_strict_id()
            pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name], t_sel)
            # (เรียกใช้ฟังก์ชัน build_pdf ที่คุณมีอยู่ได้เลย)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd
            st.session_state.pdf_blob = b"DUMMY_PDF_CONTENT" # แทนที่ด้วย build_pdf()
            st.rerun()
    else:
        st.markdown(f'''
            <div style="background:white; border:4px solid black; padding:50px 20px; text-align:center; color:black; border-radius:12px;">
                <div style="font-size:18px; color:#666;">ARCHIVE ID</div>
                <div style="font-size:22px; font-weight:bold; color:red; margin-top:10px;">{st.session_state.m_id}</div>
                <hr style="border:0; border-top:1px solid #ddd; margin:30px 0;">
                <div style="font-size:18px; color:#666;">ENCRYPTION KEY</div>
                <div style="font-size:42px; font-weight:900; letter-spacing:10px; margin-top:10px;">{st.session_state.m_pwd}</div>
            </div>
        ''', unsafe_allow_html=True)
        if st.button("RETURN"):
            st.session_state.open_sys = False
            st.session_state.pdf_blob = None
            st.rerun()

if st.session_state.open_sys:
    archive_dialog()

# ==========================================
# 3. DASHBOARD (STABLE FRAGMENT)
# ==========================================
@st.fragment(run_every=1.0)
def live_dashboard():
    m = run_calculation(sat_catalog[sat_name])
    
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;"><div style="background:white; border:5px solid black; padding:10px 60px; border-radius:100px; text-align:center;"><span style="color:black; font-size:60px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div></div>''', unsafe_allow_html=True)
    
    st.subheader("🌍 GEOSPATIAL COMMAND")
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=14, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)
    
    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], [])

    st.subheader("📊 PERFORMANCE ANALYTICS")
    g_cols = st.columns(2)
    with g_cols[0]: st.plotly_chart(go.Figure(go.Scatter(y=m["TAIL_ALT"], mode='lines+markers', line=dict(color='#00ff00'))).update_layout(title="ALTITUDE TRACK", template="plotly_dark", height=250), use_container_width=True)
    with g_cols[1]: st.plotly_chart(go.Figure(go.Scatter(y=m["TAIL_VEL"], mode='lines+markers', line=dict(color='#ffff00'))).update_layout(title="VELOCITY TRACK", template="plotly_dark", height=250), use_container_width=True)

    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

live_dashboard()