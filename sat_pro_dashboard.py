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
from geopy.geocoders import Nominatim

# --- CORE ENGINE ---
@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()
geolocator = Nominatim(user_agent="v5950_final_fix_v2")

def run_calculation(sat_obj, st_lat, st_lon, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    station = wgs84.latlon(st_lat, st_lon)
    alt, az, distance = (sat_obj - station).at(t).altaz()
    
    tele = {"TRK_LAT": f"{subpoint.latitude.degrees:.4f}", "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
            "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
            "SIG_ELEV": f"{alt.degrees:.2f} DEG", "OBC_STATUS": "ACTIVE" if alt.degrees > -5 else "SLEEP"}
    for i in range(10): tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"
    
    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "FOOTPRINT": np.sqrt(2 * 6371 * subpoint.elevation.km), "RAW_TELE": tele}

# --- PDF ENGINE (ย่อส่วนเพื่อความเร็ว) ---
def build_pdf(sat_name, addr_dict, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.cell(0, 10, f"MISSION REPORT: {sat_name}", ln=True)
    pdf.set_font("helvetica", '', 10)
    for k, v in m['RAW_TELE'].items():
        pdf.cell(0, 7, f"{k}: {v}", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- UI CONFIG ---
st.set_page_config(page_title="V5950 STABLE ZOOM", layout="wide")

if 'show_dialog' not in st.session_state: st.session_state.show_dialog = False
if 'st_lat' not in st.session_state: st.session_state.st_lat, st.session_state.st_lon = 13.75, 100.5

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 STATION ADDRESS")
    f1 = st.text_input("Sub-District", "Phra Borom")
    f2 = st.text_input("District", "Phra Nakhon")
    f3 = st.text_input("Province", "Bangkok")
    f4 = st.text_input("Country", "Thailand")
    
    if st.button("🔍 UPDATE LOCATION", use_container_width=True):
        loc = geolocator.geocode(f"{f1}, {f2}, {f3}, {f4}")
        if loc:
            st.session_state.st_lat, st.session_state.st_lon = loc.latitude, loc.longitude
            st.success("SYNCED")

    st.divider()
    # --- จุดที่แก้ไข: ลบ on_change ออกเพื่อให้ซูมได้อิสระ ---
    z1 = st.slider("Tactical Zoom", 1, 18, 12)
    z2 = st.slider("Global Zoom", 1, 10, 2)
    z3 = st.slider("Station Zoom", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.show_dialog = True

# --- DIALOG SYSTEM ---
@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    mode = st.radio("Time Mode", ["Live", "Predictive"], horizontal=True)
    t_sel = None
    if mode == "Predictive":
        c1, c2 = st.columns(2)
        d = c1.date_input("Date")
        t = c2.time_input("Time")
        t_sel = datetime.combine(d, t).replace(tzinfo=timezone.utc)
    
    if st.button("🚀 GENERATE PDF", use_container_width=True):
        m_data = run_calculation(sat_catalog[sat_name], st.session_state.st_lat, st.session_state.st_lon, t_sel)
        pdf_data = build_pdf(sat_name, {}, m_data)
        st.download_button("📥 DOWNLOAD", pdf_data, "report.pdf", use_container_width=True)
    
    if st.button("CLOSE"):
        st.session_state.show_dialog = False
        st.rerun()

if st.session_state.show_dialog:
    archive_dialog()

# --- DASHBOARD ---
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="text-align:center; margin-bottom:20px;"><div style="display:inline-block; background:white; border:4px solid black; padding:5px 50px; border-radius:100px; color:black; font-size:40px; font-weight:bold;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div></div>''', unsafe_allow_html=True)
    
    m = run_calculation(sat_catalog[sat_name], st.session_state.st_lat, st.session_state.st_lon)
    
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, foot=0):
        fig = go.Figure()
        if foot > 0: fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=zm*15, color='rgba(0, 255, 0, 0.1)')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=14, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m['FOOTPRINT'])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1")
    with m_cols[2]: draw_map(st.session_state.st_lat, st.session_state.st_lon, z3, "S1")

    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 8, 4)]))

dashboard()