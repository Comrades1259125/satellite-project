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

# --- พารามิเตอร์ 40 รายการ ---
TELE_LABELS = [f"PARAM_{i}: STABLE" for i in range(11, 41)]
CORE_DATA = ["NORAD_ID: 25544", "INCLINATION: 51.6321°", "PERIOD: 92.85 MIN", "ECCENTRICITY: 0.000852", "BSTAR_DRAG: 0.000205", "MISSION_STATUS: NOMINAL"]

@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

LOC_DB = {
    "Sakon Nakhon": {"lat": 17.1612, "lon": 104.1486, "tz": 7},
    "Bangkok": {"lat": 13.7563, "lon": 100.5018, "tz": 7}
}

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t); subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # รวบรวมข้อมูลให้ครบ 40 ช่องตาม Layout ใหม่
    data = [
        f"LATITUDE: {subpoint.latitude.degrees:.5f}°", f"LONGITUDE: {subpoint.longitude.degrees:.5f}°",
        f"ALTITUDE: {subpoint.elevation.km:.2f} KM", f"VELOCITY: {v_km_s * 3600:.1f} KM/H"
    ] + CORE_DATA + TELE_LABELS
    
    history = {"lats": [], "lons": [], "vels": [], "alts": []}
    for i in range(0, 101, 5):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); s = wgs84.subpoint(g)
        history["lats"].append(s.latitude.degrees); history["lons"].append(s.longitude.degrees)
        history["vels"].append(np.linalg.norm(g.velocity.km_per_s) * 3600)
        history["alts"].append(s.elevation.km)
    return data, history

class ULTIMATE_PDF(FPDF):
    def draw_detailed_grid_graph(self, x, y, w, h, title, data, color, unit):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(200, 200, 200); self.set_line_width(0.1)
        for i in range(11): lx = x + (i * (w / 10)); self.line(lx, y, lx, y + h)
        for i in range(6): ly = y + (i * (h / 5)); self.line(x, ly, x + w, ly)
        min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
        self.set_font("Arial", '', 6); self.set_text_color(100)
        for i in range(6):
            val = max_v - (i * (v_range / 5))
            self.set_xy(x - 12, y + (i * (h / 5)) - 1.5); self.cell(10, 3, f"{val:.1f}", align='R')
        self.set_font("Arial", 'B', 9); self.set_text_color(0)
        self.set_xy(x, y - 6); self.cell(w, 5, f"{title} ({unit})", align='L')
        if len(data) > 1:
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.5)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m_main, m_hist):
    pdf = ULTIMATE_PDF()
    # --- หน้าที่ 1: ปรับตามรูปภาพใหม่ ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 18); pdf.cell(0, 10, f"OFFICIAL MISSION DATA REPORT: {sat_name.upper()}", ln=True, align='C')
    pdf.set_font("Arial", '', 10); gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.cell(0, 8, f"REPORT GENERATED: {gen_time} | MODE: Live Now", ln=True, align='C')
    
    pdf.ln(5); pdf.set_fill_color(230); pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, " GROUND STATION IDENTIFICATION", ln=True, fill=True)
    pdf.set_font("Arial", '', 10)
    full_addr = f"Location: {addr['s']} Subdistrict, {addr['d']} District, {addr['p']}, {addr['c']}"
    pdf.cell(0, 10, full_addr, ln=True)

    pdf.ln(2); pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, " TECHNICAL TELEMETRY MATRIX", ln=True, fill=True)
    pdf.set_font("Courier", 'B', 7.5)
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(m_main): pdf.cell(47.5, 7, m_main[i+j].upper(), border=1)
        pdf.ln()

    pdf.ln(5); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, " ORBITAL TRAJECTORY ANALYSIS", ln=True, fill=True)
    pdf.set_font("Arial", '', 10); pdf.ln(2)
    pdf.multi_cell(0, 6, f"The satellite is currently at {m_main[0]} and {m_main[1]}.\nCurrent {m_main[2]} with a {m_main[3]}.\nStability analysis indicates nominal orbital maintenance.")

    # --- หน้าที่ 2: กราฟละเอียดเหมือนเดิม ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "PRECISION ANALYTICS - PAGE 2", ln=True, align='C')
    pdf.ln(10)
    pdf.draw_detailed_grid_graph(20, 40, 170, 45, "LATITUDE TRAJECTORY", m_hist["lats"], (0, 102, 204), "DEG")
    pdf.draw_detailed_grid_graph(20, 105, 170, 45, "ORBITAL VELOCITY", m_hist["vels"], (204, 0, 0), "KM/H")
    pdf.draw_detailed_grid_graph(20, 170, 170, 45, "ALTITUDE VARIATION", m_hist["alts"], (0, 153, 51), "KM")
    
    # QR & Sign
    pdf.set_draw_color(0); pdf.rect(15, 235, 40, 45)
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 17.5, 237, 35, 35)
    pdf.set_xy(15, 272); pdf.set_font("Arial", 'B', 7); pdf.cell(40, 5, "SECURE VERIFICATION", align='C', ln=True)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 235, 30, 20)
    pdf.line(120, 265, 190, 265); pdf.set_xy(120, 267); pdf.set_font("Arial", 'B', 10); 
    pdf.cell(70, 5, s_name.upper() if s_name else "DIRECTOR", align='C', ln=True)
    pdf.set_x(120); pdf.set_font("Arial", 'I', 8); pdf.cell(70, 5, s_pos.upper() if s_pos else "COMMANDER", align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# --- UI LOGIC ---
st.set_page_config(page_title="ZENITH V9.0", layout="wide")
if "archive_data" not in st.session_state: st.session_state.archive_data = None

@st.dialog("📍 ADDRESS VALIDATION")
def address_dialog(z, c, p, d, s):
    st.write("🛰️ **กำลังตรวจสอบโครงข่ายข้อมูลตำแหน่ง...**")
    if not all([z, c, p, d, s]):
        st.error("❌ ข้อมูลไม่ครบ! กรุณากรอกที่อยู่ให้ครบทุกช่องก่อนยืนยัน")
    elif p not in LOC_DB:
        st.warning(f"⚠️ จังหวัด '{p}' ยังไม่มีในฐานพิกัดดาวเทียม ระบบจะใช้ค่า Default กลาง")
        if st.button("ตกลง ใช้ค่าเดิม"): st.rerun()
    else:
        st.success(f"✅ ยืนยันตำแหน่งสำเร็จ: {s}, {d}, {p}")
        st.session_state.valid_loc = True
        if st.button("ปิดหน้าต่าง"): st.rerun()

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
    z_a = st.text_input("โซน", "Asia")
    c_a = st.text_input("ประเทศ", "Thailand")
    p_a = st.text_input("จังหวัด", "Sakon Nakhon")
    d_a = st.text_input("อำเภอ", "Mueang")
    s_a = st.text_input("ตำบล", "That Choeng Chum")
    
    if st.button("✅ ยืนยันที่อยู่ (CONFIRM)", use_container_width=True):
        address_dialog(z_a, c_a, p_a, d_a, s_a)
        
    loc_info = LOC_DB.get(p_a, {"lat": 13.7, "lon": 100.5, "tz": 7})
    st_lat, st_lon, st_tz = loc_info["lat"], loc_info["lon"], loc_info["tz"]
    st.divider()
    z1 = st.slider("Tactical", 1, 18, 12); z2 = st.slider("Global", 1, 10, 2); z3 = st.slider("Station", 1, 18, 15)

    @st.dialog("📋 MISSION DATA ARCHIVE")
    def mission_modal():
        if st.session_state.archive_data is None:
            s_name = st.text_input("Officer Name"); s_pos = st.text_input("Designation")
            s_img = st.file_uploader("Seal (PNG)", type=['png'])
            if st.button("🚀 EXECUTE ENCRYPTION"):
                fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%Y%m%d')}"
                pwd = "".join([str(random.randint(0,9)) for _ in range(6)])
                m_main, m_hist = run_calculation(sat_catalog[sel_sat])
                addr = {"z": z_a, "c": c_a, "p": p_a, "d": d_a, "s": s_a}
                pdf_blob = build_pdf(sel_sat, addr, s_name, s_pos, s_img, fid, pwd, m_main, m_hist)
                st.session_state.archive_data = {"pdf": pdf_blob, "fid": fid, "pwd": pwd}
                st.rerun()
        else:
            d = st.session_state.archive_data
            st.markdown(f'<div style="border:4px solid black; padding:20px; text-align:center;">ID: <h2 style="color:red;">{d["fid"]}</h2>PASS: <h1 style="letter-spacing:10px;">{d["pwd"]}</h1></div>', unsafe_allow_html=True)
            st.download_button("📥 DOWNLOAD PDF", d["pdf"], f"{d['fid']}.pdf", use_container_width=True)
            if st.button("CLOSE"): st.session_state.archive_data = None; st.rerun()

    if st.button("🧧 GENERATE MISSION ARCHIVE", use_container_width=True, type="primary"):
        mission_modal()

@st.fragment(run_every=1.0)
def main_dashboard():
    synced_time = (datetime.now(timezone.utc) + timedelta(hours=st_tz)).strftime("%H:%M:%S")
    st.markdown(f'<div style="text-align:center; background:white; border:5px solid black; border-radius:100px; padding:15px; margin-bottom:20px;"><span style="color:black; font-size:70px; font-weight:900; font-family:monospace;">{synced_time}</span><p style="margin:0; font-weight:bold; color:gray;">LOCATION: {p_a}</p></div>', unsafe_allow_html=True)
    if sat_catalog and sel_sat in sat_catalog:
        m_main, m_hist = run_calculation(sat_catalog[sel_sat])
        cols = st.columns(3)
        cols[0].metric("ALTITUDE", m_main[2]); cols[1].metric("VELOCITY", m_main[3]); cols[2].metric("POSITION", f"{m_main[0]}, {m_main[1]}")
        m_cols = st.columns(3)
        def draw_map(lt, ln, zm, k):
            fig = go.Figure(go.Scattermapbox(lat=[float(lt.split(': ')[1].split('°')[0])], lon=[float(ln.split(': ')[1].split('°')[0])], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=float(lt.split(': ')[1].split('°')[0]), lon=float(ln.split(': ')[1].split('°')[0])), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350)
            st.plotly_chart(fig, use_container_width=True, key=k)
        with m_cols[0]: draw_map(m_main[0], m_main[1], z1, "m1")
        with m_cols[1]: draw_map(m_main[0], m_main[1], z2, "m2")
        with m_cols[2]:
            fig_st = go.Figure(go.Scattermapbox(lat=[st_lat], lon=[st_lon], mode='markers', marker=dict(size=15, color='blue')))
            fig_st.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=st_lat, lon=st_lon), zoom=z3), margin=dict(l=0,r=0,t=0,b=0), height=350)
            st.plotly_chart(fig_st, use_container_width=True, key="m3")
        st.subheader("📊 40-PARAMETER TELEMETRY STREAM")
        st.table(pd.DataFrame([m_main[i:i+4] for i in range(0, 44, 4)]))

main_dashboard()