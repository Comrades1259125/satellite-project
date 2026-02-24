import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import qrcode
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84

# ==========================================
# 1. CORE ENGINE
# ==========================================
@st.cache_resource
def init_satellite_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_satellite_system()
ts = load.timescale()

# พิกัดจำลองสำหรับแผนที่ที่ 3 ตามที่อยู่ (สามารถขยายเพิ่มได้)
LOC_DB = {
    "Bangkok": {"lat": 13.7563, "lon": 100.5018},
    "Sakon Nakhon": {"lat": 17.1612, "lon": 104.1486},
    "Chiang Mai": {"lat": 18.7883, "lon": 98.9853},
    "Phuket": {"lat": 7.8804, "lon": 98.3923}
}

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    tele = {"TRK_LAT": f"{subpoint.latitude.degrees:.4f}", "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
            "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:,.2f} KM/H"}
    for i in range(36): tele[f"SENSOR_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    lats, lons = [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        ps = wgs84.subpoint(sat_obj.at(pt))
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "RAW_TELE": tele}

# ==========================================
# 2. PDF ENGINE
# ==========================================
def build_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "OFFICIAL DATA ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", 'B', 8)
    addr_str = f"ZONE: {addr['z']} | COUNTRY: {addr['c']} | PROVINCE: {addr['p']} | DISTRICT: {addr['d']} | SUB-DISTRICT: {addr['s']}"
    pdf.cell(0, 8, addr_str.upper(), border=1, ln=True, align='C')
    pdf.ln(5); items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("Courier", '', 7); pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 20, 230, 30, 30)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 230, 30, 20)
    pdf.set_xy(120, 255); pdf.set_font("Arial", 'B', 10); pdf.cell(60, 5, s_name.upper(), align='C', ln=True)
    pdf.set_x(120); pdf.set_font("Arial", 'I', 8); pdf.cell(60, 5, s_pos.upper(), align='C')
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. UI INTERFACE
# ==========================================
st.set_page_config(page_title="ZENITH V7.9", layout="wide")

if 'show_archive' not in st.session_state: st.session_state.show_archive = False
if 'pdf_ready' not in st.session_state: st.session_state.pdf_ready = None

with st.sidebar:
    st.header("🛰️ COMMAND PANEL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()) if sat_catalog else ["Loading..."])
    
    st.subheader("📍 ADDRESS SETTINGS")
    z_a = st.text_input("โซน", "Asia")
    c_a = st.text_input("ประเทศ", "Thailand")
    p_a = st.text_input("จังหวัด", "Bangkok")
    d_a = st.text_input("อำเภอ", "Phra Nakhon")
    s_a = st.text_input("ตำบล", "Phra Borom")
    
    # พิกัดแผนที่ 3 จะเปลี่ยนตามจังหวัด
    st_lat = LOC_DB.get(p_a, {"lat": 13.75, "lon": 100.5})["lat"]
    st_lon = LOC_DB.get(p_a, {"lat": 13.75, "lon": 100.5})["lon"]

    if st.button("✅ CONFIRM & LOCK ADDRESS", use_container_width=True):
        st.success(f"Locked to {p_a}")

    st.divider()
    st.subheader("🔍 MULTI-ZOOM")
    z1 = st.slider("Tactical", 1, 18, 12)
    z2 = st.slider("Global", 1, 10, 2)
    z3 = st.slider("Station", 1, 18, 15)
    
    if st.button("🧧 GENERATE MISSION ARCHIVE", use_container_width=True, type="primary"):
        st.session_state.show_archive = True

# POPUP หน้าดาวน์โหลด (แก้ไข st.ln Error)
if st.session_state.show_archive:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_modal():
        if st.session_state.pdf_ready is None:
            mode = st.radio("Calculation Mode", ["Live", "Predictive"], horizontal=True)
            t_target = None
            if mode == "Predictive":
                col1, col2 = st.columns(2)
                d_p = col1.date_input("Date")
                t_p = col2.time_input("Time")
                t_target = datetime.combine(d_p, t_p).replace(tzinfo=timezone.utc)
            
            st.divider()
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Title", "CHIEF COMMANDER")
            s_img = st.file_uploader("Upload Digital Seal (PNG)", type=['png'])
            
            if st.button("🚀 BUILD ARCHIVE", use_container_width=True):
                fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%m%d')}"
                pwd = "".join([str(random.randint(0,9)) for _ in range(6)])
                m_data = run_calculation(sat_catalog[sel_sat], t_target)
                addr_map = {"z": z_a, "c": c_a, "p": p_a, "d": d_a, "s": s_a}
                st.session_state.pdf_ready = build_archive(sel_sat, addr_map, s_name, s_pos, s_img, fid, pwd, m_data)
                st.session_state.fid, st.session_state.pwd = fid, pwd
                st.rerun()
        else:
            # UI เหมือนรูป 1 และ 2
            st.markdown(f"""
                <div style="border: 3px solid black; padding: 25px; border-radius: 15px; text-align: center; background-color: white;">
                    <p style="color: gray; font-weight: bold;">DOCUMENT ARCHIVE ID</p>
                    <h2 style="color: red; font-weight: 900;">{st.session_state.fid}</h2>
                    <hr>
                    <p style="color: gray; font-weight: bold;">ENCRYPTION KEY</p>
                    <h1 style="color: black; font-weight: 900; font-size: 50px; letter-spacing: 8px;">{st.session_state.pwd}</h1>
                </div>
            """, unsafe_allow_html=True)
            st.write("") # แทน st.ln
            st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_ready, f"{st.session_state.fid}.pdf", use_container_width=True)
            if st.button("RETURN", use_container_width=True):
                st.session_state.show_archive = False
                st.session_state.pdf_ready = None
                st.rerun()
    archive_modal()

@st.fragment(run_every=1.0)
def main_view():
    st.markdown(f'''<div style="text-align:center; background:white; border:5px solid black; padding:10px; border-radius:100px; margin-bottom:20px;">
                <span style="color:black; font-size:55px; font-weight:900; font-family:monospace;">{datetime.now().strftime("%H:%M:%S")}</span></div>''', unsafe_allow_html=True)
    
    if sat_catalog and sel_sat in sat_catalog:
        m = run_calculation(sat_catalog[sel_sat])
        
        # Triple Map: ใบที่ 3 ขยับตามจังหวัดที่กรอก
        m_cols = st.columns(3)
        def draw_map(lt, ln, zm, k, tl, tn, title):
            st.caption(f"**{title}**")
            fig = go.Figure()
            if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
            fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)

        with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "m1", m["TAIL_LAT"], m["TAIL_LON"], "TACTICAL VIEW")
        with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "m2", m["TAIL_LAT"], m["TAIL_LON"], "GLOBAL VIEW")
        with m_cols[2]: draw_map(st_lat, st_lon, z3, "m3", [], [], f"STATION: {p_a}")

        st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

main_view()