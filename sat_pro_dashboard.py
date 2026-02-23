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

# ==========================================
# 1. CORE ENGINE & GEOPY
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

def get_station_coords(sub, dist, prov, country):
    full_address = f"{sub}, {dist}, {prov}, {country}"
    try:
        geolocator = Nominatim(user_agent="v5950_final_system")
        location = geolocator.geocode(full_address)
        if location: return location.latitude, location.longitude
    except: pass
    return 13.7563, 100.5018

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # คำนวณเส้นย้อนหลัง 100 นาที (TAIL)
    lats, lons = [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        ps = wgs84.subpoint(sat_obj.at(pt))
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        
    tele = {"ALT": f"{subpoint.elevation.km:.2f} KM", "VEL": f"{v_km_s*3600:.2f} KM/H", "STATUS": "NOMINAL"}
    
    return {
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "RAW_TELE": tele
    }

# ==========================================
# 2. PDF ENGINE (กู้คืนระบบโหลด)
# ==========================================
def build_pdf(sat_name, addr, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.cell(0, 10, f"MISSION REPORT: {sat_name}", ln=True, align='C')
    pdf.set_font("helvetica", '', 12)
    pdf.cell(0, 10, f"STATION: {addr['sub']}, {addr['dist']}, {addr['prov']}", ln=True)
    pdf.cell(0, 10, f"COORDINATES: {m['LAT']:.4f}, {m['LON']:.4f}", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. INTERFACE (3 MAPS + SIDEBAR)
# ==========================================
st.set_page_config(page_title="V5950 FULL RECOVERY", layout="wide")

if 'st_lat' not in st.session_state:
    st.session_state.st_lat, st.session_state.st_lon = 13.7563, 100.5018
if 'open_sys' not in st.session_state: st.session_state.open_sys = False

def reset_sys():
    st.session_state.open_sys = False

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()), on_change=reset_sys)
    
    st.subheader("📍 STATION LOOKUP")
    a1 = st.text_input("Sub-District", "Phra Borom", on_change=reset_sys)
    a2 = st.text_input("District", "Phra Nakhon", on_change=reset_sys)
    a3 = st.text_input("Province", "Bangkok", on_change=reset_sys)
    a4 = st.text_input("Country", "Thailand", on_change=reset_sys)
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    
    if st.button("🔍 FETCH & LOCK STATION", use_container_width=True):
        lat, lon = get_station_coords(a1, a2, a3, a4)
        st.session_state.st_lat, st.session_state.st_lon = lat, lon
        st.toast("STATION UPDATED")

    z1 = st.slider("Tactical Zoom", 1, 18, 12, on_change=reset_sys)
    z2 = st.slider("Global Zoom", 1, 10, 2, on_change=reset_sys)
    z3 = st.slider("Station Zoom", 1, 18, 15, on_change=reset_sys)
    
    st.markdown("---")
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"): 
        st.session_state.open_sys = True

# ระบบ Pop-up รายงาน
@st.dialog("📋 ARCHIVE ACCESS")
def archive_dialog():
    m_data = run_calculation(sat_catalog[sat_name])
    pdf_blob = build_pdf(sat_name, addr_data, m_data)
    st.write("REPORT GENERATED SUCCESSFULLY")
    st.download_button("📥 DOWNLOAD PDF", pdf_blob, "report.pdf", use_container_width=True)
    if st.button("CLOSE"): st.session_state.open_sys = False; st.rerun()

if st.session_state.open_sys: archive_dialog()

# ==========================================
# 4. DASHBOARD (แผนที่ 3 อัน + เส้น Tail)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    m = run_calculation(sat_catalog[sat_name])
    
    st.subheader("🌍 GEOSPATIAL COMMAND CENTER")
    m_cols = st.columns([1, 1, 1])
    
    def draw_map(lt, ln, zm, k, tl=None, tn=None, color='red'):
        fig = go.Figure()
        if tl and tn: # วาดเส้นสีเหลือง
            fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color=color)))
        fig.update_layout(
            mapbox=dict(
                style="white-bg", 
                layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], 
                center=dict(lat=lt, lon=ln), zoom=zm
            ), margin=dict(l=0,r=0,t=0,b=0), height=400, showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True, key=k)
        
    with m_cols[0]:
        st.caption("📡 TACTICAL VIEW")
        draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
        
    with m_cols[1]:
        st.caption("🌐 GLOBAL TRACK")
        draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    
    with m_cols[2]:
        st.caption(f"🏠 STATION: {a2.upper()}")
        draw_map(st.session_state.st_lat, st.session_state.st_lon, z3, "S1", color='cyan')

    # Telemetry Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("LATITUDE", f"{m['LAT']:.4f}")
    c2.metric("LONGITUDE", f"{m['LON']:.4f}")
    c3.metric("ALTITUDE", f"{m['ALT_VAL']:.2f} KM")

dashboard()