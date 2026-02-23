import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timedelta, timezone
from fpdf import FPDF  # ต้องติดตั้ง fpdf2
from pypdf import PdfReader, PdfWriter
import qrcode
from io import BytesIO
from skyfield.api import load, wgs84
from geopy.geocoders import Nominatim
from PIL import Image

# 1. ระบบจัดการข้อมูล (ถ้าโหลด TLE ไม่ได้จะใช้ค่า Default เพื่อไม่ให้จอมืด)
@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except:
        st.error("📡 ไม่สามารถเชื่อมต่อฐานข้อมูลดาวเทียมได้ ระบบจะรันในโหมดจำลอง")
        return {}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    
    # กรณีไม่มีดาวเทียม (กันจอมืด)
    if not sat_obj:
        return {"LAT": 13.7, "LON": 100.5, "ALT_VAL": 400, "VEL_VAL": 27000, 
                "TAIL_LAT": [13, 14], "TAIL_LON": [100, 101], "TAIL_ALT": [400, 401], 
                "TAIL_VEL": [27000, 27100], "RAW_TELE": {"STATUS": "OFFLINE"}}

    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 20):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)
    
    return {
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels,
        "RAW_TELE": {"TRK_LAT": f"{subpoint.latitude.degrees:.2f}", "TRK_ALT": f"{subpoint.elevation.km:.2f} KM"}
    }

# 2. อินเตอร์เฟซหลัก
st.set_page_config(page_title="V5950 RECOVERY", layout="wide")

# ส่วนป้องกันจอมืด: ถ้าเกิด Error ในโค้ดหลัก ให้โชว์ Error แทนการดับไปเลย
try:
    with st.sidebar:
        st.header("🛰️ CONTROL PANEL")
        if sat_catalog:
            sat_name = st.selectbox("เลือกดาวเทียม", list(sat_catalog.keys()))
            selected_sat = sat_catalog[sat_name]
        else:
            sat_name = "SIMULATOR"
            selected_sat = None

        st.subheader("📍 พิกัดสถานี")
        a1 = st.text_input("ตำบล", "Phra Borom")
        a2 = st.text_input("อำเภอ", "Phra Nakhon")
        
        z1 = st.slider("ซูม Tactical", 1, 18, 12)
        z2 = st.slider("ซูม Global", 1, 10, 2)
        
        if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
            st.session_state.open_sys = True

    # 3. ส่วนแสดงผล Dashboard
    st.title("🌍 Satellite Tracking System")
    
    m = run_calculation(selected_sat)
    
    col1, col2 = st.columns(2)
    
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        fig.update_layout(
            mapbox=dict(style="carto-darkmatter", center=dict(lat=lt, lon=ln), zoom=zm),
            margin=dict(l=0,r=0,t=0,b=0), height=400, showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True, key=k)

    with col1:
        st.subheader("📡 Tactical View")
        draw_map(m['LAT'], m['LON'], z1, "map1", m['TAIL_LAT'], m['TAIL_LON'])
        
    with col2:
        st.subheader("🌐 Global Track")
        draw_map(m['LAT'], m['LON'], z2, "map2", m['TAIL_LAT'], m['TAIL_LON'])

    st.subheader("📊 Telemetry Data")
    st.write(pd.DataFrame([m['RAW_TELE']]))

except Exception as e:
    st.error(f"⚠️ เกิดข้อผิดพลาดทางเทคนิค: {e}")
    st.info("แนะนำให้ตรวจสอบการติดตั้ง Library ใน requirements.txt อีกครั้ง")