import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
import qrcode
from io import BytesIO
from skyfield.api import load, wgs84

# ==========================================
# 1. CORE DATA & GEOLOCATION DATABASE
# ==========================================
# ฐานข้อมูลพิกัดแบบ Manual สำหรับสถานีภาคพื้นดิน
GEO_DB = {
    "BANGKOK": {"lat": 13.7563, "lon": 100.5018},
    "PHRA NAKHON": {"lat": 13.7589, "lon": 100.4974},
    "PATHUM WAN": {"lat": 13.7367, "lon": 100.5231},
    "CHATTUCHAK": {"lat": 13.8285, "lon": 100.5597},
    "CHIANG MAI": {"lat": 18.7883, "lon": 98.9853},
    "CHONBURI": {"lat": 13.3611, "lon": 100.9847},
    "KHON KAEN": {"lat": 16.4322, "lon": 102.8236},
    "PHUKET": {"lat": 7.8804, "lon": 98.3922}
}

def get_real_coords(dist, prov):
    # พยายามหาจากชื่อเขตก่อน ถ้าไม่เจอหาจากชื่อจังหวัด
    d_key = dist.upper().strip()
    p_key = prov.upper().strip()
    
    if d_key in GEO_DB: return GEO_DB[d_key]["lat"], GEO_DB[d_key]["lon"]
    if p_key in GEO_DB: return GEO_DB[p_key]["lat"], GEO_DB[p_key]["lon"]
    
    # ถ้าไม่เจอเลย ให้กลับไปที่กรุงเทพฯ เป็นค่าเริ่มต้น
    return 13.7563, 100.5018

@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj):
    t = ts.now()
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees, 
            "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}"}

# ==========================================
# 2. INTERFACE
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

def reset_sys():
    st.session_state.open_sys = False

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()), on_change=reset_sys)
    
    st.subheader("📍 STATION LOCATION")
    a1 = st.text_input("Sub-District", "Phra Borom", on_change=reset_sys)
    a2 = st.text_input("District (e.g. Phra Nakhon)", "Phra Nakhon", on_change=reset_sys)
    a3 = st.text_input("Province (e.g. Bangkok)", "Bangkok", on_change=reset_sys)
    
    # ดึงพิกัดจากฐานข้อมูล GEO_DB
    st_lat, st_lon = get_real_coords(a2, a3)
    
    if st.button("📍 CONFIRM & LOCK STATION", use_container_width=True):
        st.success(f"STATION LOCKED AT: {st_lat}, {st_lon}")
        reset_sys()

    z1 = st.slider("Tactical Zoom", 1, 18, 12, on_change=reset_sys)
    z2 = st.slider("Global Zoom", 1, 10, 2, on_change=reset_sys)
    z3 = st.slider("Station Zoom", 1, 18, 15, on_change=reset_sys)

# ==========================================
# 3. DASHBOARD
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    m = run_calculation(sat_catalog[sat_name])
    
    st.subheader("🌍 GEOSPATIAL COMMAND")
    m_cols = st.columns([1, 1, 1])
    
    def draw_map(lt, ln, zm, k, color='red', label="ASSET"):
        fig = go.Figure()
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers+text', 
                                       marker=dict(size=15, color=color),
                                       text=[label], textposition="top right"))
        fig.update_layout(
            mapbox=dict(
                style="white-bg", 
                layers=[{"below": 'traces', "sourcetype": "raster", 
                         "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], 
                center=dict(lat=lt, lon=ln), zoom=zm
            ), margin=dict(l=0,r=0,t=0,b=0), height=400, showlegend=False, dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, key=k, config={'scrollZoom': False})
        
    with m_cols[0]: 
        st.write("📡 ASSET TRACKING (CLOSE)")
        draw_map(m['LAT'], m['LON'], z1, "T1")
        
    with m_cols[1]: 
        st.write("🌐 GLOBAL ORBIT")
        draw_map(m['LAT'], m['LON'], z2, "G1")
    
    with m_cols[2]: 
        st.write(f"🏠 STATION: {a2.upper()}")
        # แผนที่ 3 ล็อกตามพิกัดที่เราหาจาก GEO_DB
        draw_map(st_lat, st_lon, z3, "S1", color='cyan', label="STATION")

dashboard()