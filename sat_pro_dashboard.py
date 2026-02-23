import streamlit as st
import plotly.graph_objects as go
from geopy.geocoders import Nominatim # <--- ตัวเชื่อมฐานข้อมูลภายนอก
import pandas as pd
import numpy as np
import random
from datetime import datetime, timezone
from skyfield.api import load, wgs84

# ==========================================
# 1. EXTERNAL DATABASE ENGINE (Geopy)
# ==========================================
def get_coordinates_from_api(sub, dist, prov, country):
    # รวมชื่อที่อยู่เป็น String เดียวเพื่อไปค้นหาในฐานข้อมูลโลก
    full_address = f"{sub}, {dist}, {prov}, {country}"
    
    try:
        # เรียกใช้ Nominatim API (ฟรี)
        geolocator = Nominatim(user_agent="v5950_satellite_tracker")
        location = geolocator.geocode(full_address)
        
        if location:
            return location.latitude, location.longitude
        else:
            # ถ้าหาไม่เจอ ให้คืนค่าพิกัดกลางของจังหวัด หรือกรุงเทพฯ
            return 13.7563, 100.5018
    except:
        return 13.7563, 100.5018

# ==========================================
# 2. CORE SYSTEM (คงเดิม)
# ==========================================
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
    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees}

# ==========================================
# 3. INTERFACE & SIDEBAR
# ==========================================
st.set_page_config(page_title="V5950 EXTERNAL DB", layout="wide")

if 'st_lat' not in st.session_state:
    st.session_state.st_lat, st.session_state.st_lon = 13.7563, 100.5018

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    
    st.subheader("🌐 GLOBAL ADDRESS LOOKUP")
    a1 = st.text_input("Sub-District / Place", "Phra Borom")
    a2 = st.text_input("District / City", "Phra Nakhon")
    a3 = st.text_input("Province / State", "Bangkok")
    a4 = st.text_input("Country", "Thailand")
    
    if st.button("🔍 FETCH EXTERNAL COORDINATES", use_container_width=True, type="primary"):
        with st.spinner("Searching Global Database..."):
            lat, lon = get_coordinates_from_api(a1, a2, a3, a4)
            st.session_state.st_lat, st.session_state.st_lon = lat, lon
            st.success(f"Found: {lat:.4f}, {lon:.4f}")

    z3 = st.slider("Station Zoom", 1, 18, 15)

# ==========================================
# 4. DASHBOARD (แผนที่อันที่ 3)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    m = run_calculation(sat_catalog[sat_name])
    cols = st.columns([2, 1]) # แบ่งฝั่งดาวเทียม กับ ฝั่งสถานี
    
    with cols[0]:
        st.write("📡 SATELLITE LIVE TRACK")
        fig = go.Figure(go.Scattermapbox(lat=[m['LAT']], lon=[m['LON']], marker=dict(size=15, color='red')))
        fig.update_layout(
            mapbox=dict(style="white-bg", 
                         layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
                         center=dict(lat=m['LAT'], lon=m['LON']), zoom=3),
            margin=dict(l=0,r=0,t=0,b=0), height=500, dragmode=False)
        st.plotly_chart(fig, use_container_width=True, key="sat_map")

    with cols[1]:
        st.write(f"🏠 STATION LOCATION (EXTERNAL DB)")
        # แผนที่ที่ 3 ดึงจากพิกัดที่ Fetch มาจากฐานข้อมูลภายนอก
        fig_st = go.Figure(go.Scattermapbox(lat=[st.session_state.st_lat], lon=[st.session_state.st_lon], 
                                            marker=dict(size=20, color='cyan')))
        fig_st.update_layout(
            mapbox=dict(style="white-bg", 
                         layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
                         center=dict(lat=st.session_state.st_lat, lon=st.session_state.st_lon), zoom=z3),
            margin=dict(l=0,r=0,t=0,b=0), height=500, dragmode=False)
        st.plotly_chart(fig_st, use_container_width=True, key="st_map")

dashboard()