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
# 1. CORE ENGINE
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try:
        return {sat.name: sat for sat in load.tle_file(url)}
    except:
        return {}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "SYS_STATUS": "NOMINAL",
        "OBC_STATUS": "ACTIVE",
        "GEN_TIME": t_input.strftime("%H:%M:%S")
    }
    # แก้ไข Syntax Error ตรง i+1 แล้ว
    for i in range(33): 
        tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt)
        ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees)
        lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km)
        vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, "RAW_TELE": tele}

# ==========================================
# 2. PDF ENGINE
# ==========================================
def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 24); pdf.cell(0, 12, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 14); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.ln(10)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", '', 7); pdf.cell(47.25, 8, f" {items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    
    pdf.ln(30); pdf.line(105, 250, 195, 250)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 135, 220, 30, 25)
    pdf.set_xy(105, 252); pdf.set_font("helvetica", 'B', 11); pdf.cell(90, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(105); pdf.set_font("helvetica", 'I', 9); pdf.cell(90, 5, s_pos.upper(), align='C')
    
    raw = BytesIO(pdf.output())
    reader = PdfReader(raw); writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (STABLE & NO-POPUP)
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    # ป้องกันกรณีโหลด TLE ไม่สำเร็จ
    asset_list = list(sat_catalog.keys()) if sat_catalog else ["NO DATA"]
    sat_name = st.selectbox("ASSET", asset_list)
    
    st.subheader("📍 STATION LOCATION")
    a1 = st.text_input("Sub-District", "Phra Borom")
    a2 = st.text_input("District", "Phra Nakhon")
    a3 = st.text_input("Province", "Bangkok")
    a4 = st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    
    st.divider()
    z1 = st.slider("Tactical Zoom", 1, 18, 12)
    z2 = st.slider("Global Zoom", 1, 10, 2)
    z3 = st.slider("Station Zoom", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.pdf_blob = None
        st.session_state.open_sys = True

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Time Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            t_sel = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
        
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position Sub-text", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        
        if st.button("🚀 INITIATE", use_container_width=True):
            fid = f"REF-{random.randint(100, 999)}"
            pwd = ''.join(random.choices(string.digits, k=6))
            if sat_name != "NO DATA":
                m_data = run_calculation(sat_catalog[sat_name], t_sel)
                st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
                st.session_state.m_id, st.session_state.m_pwd = fid, pwd
                st.rerun()
    else:
        st.markdown(f'''
            <div style="background:white; border:4px solid black; padding:20px; text-align:center; color:black;">
                <div style="font-size:18px;">ARCHIVE ID: <b>{st.session_state.m_id}</b></div>
                <div style="font-size:28px; font-weight:900; margin-top:10px;">PASS: {st.session_state.m_pwd}</div>
            </div>
        ''', unsafe_allow_html=True)
        
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        
        if st.button("RETURN", use_container_width=True):
            st.session_state.open_sys = False
            st.session_state.pdf_blob = None
            st.rerun()

if st.session_state.open_sys:
    archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;"><div style="background:white; border:5px solid black; padding:10px 60px; border-radius:100px; text-align:center;"><span style="color:black; font-size:60px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div></div>''', unsafe_allow_html=True)
    
    if sat_catalog and sat_name != "NO DATA":
        m = run_calculation(sat_catalog[sat_name])
        m_cols = st.columns(3)
        def draw_map(lt, ln, zm, k, tl, tn):
            fig = go.Figure()
            fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
            fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=14, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)
            
        with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
        with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
        with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], [])

        st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))
    else:
        st.error("TLE Data not available. Check internet connection.")

dashboard()