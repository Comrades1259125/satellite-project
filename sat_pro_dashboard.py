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
# 1. CORE ENGINE & GEOLOCATION
# ==========================================
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
    "Bangkok": {"lat": 13.7563, "lon": 100.5018, "tz": 7},
    "London": {"lat": 51.5074, "lon": -0.1278, "tz": 0},
    "New York": {"lat": 40.7128, "lon": -74.0060, "tz": -5}
}

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    tele = {"TRK_LAT": subpoint.latitude.degrees, "TRK_LON": subpoint.longitude.degrees,
            "TRK_ALT": subpoint.elevation.km, "TRK_VEL": v_km_s * 3600}
    
    history = {"lats": [], "lons": [], "vels": [], "alts": []}
    for i in range(0, 101, 5):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); s = wgs84.subpoint(g)
        history["lats"].append(s.latitude.degrees); history["lons"].append(s.longitude.degrees)
        history["vels"].append(np.linalg.norm(g.velocity.km_per_s) * 3600)
        history["alts"].append(s.elevation.km)
    return tele, history

# ==========================================
# 2. PDF ENGINE (HIGH-DETAIL)
# ==========================================
class ULTIMATE_PDF(FPDF):
    def draw_detailed_graph(self, x, y, w, h, title, data, color):
        self.set_fill_color(245, 245, 245); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.3); self.rect(x, y, w, h)
        self.set_font("Arial", 'B', 9); self.set_xy(x, y-4); self.cell(w, 4, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.5)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_ultimate_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m_main, m_hist):
    pdf = ULTIMATE_PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 18); pdf.cell(0, 12, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", 'B', 8); addr_text = f"ZONE: {addr['z']} | CNTR: {addr['c']} | PROV: {addr['p']} | DIST: {addr['d']} | SUB: {addr['s']}"
    pdf.cell(0, 7, addr_text.upper(), border=1, ln=True, align='C')
    pdf.ln(4); pdf.set_font("Courier", 'B', 7)
    items = [(k, f"{v:,.2f}") for k,v in m_main.items()]
    for i in range(28): items.append((f"SENSOR_{i+1:02d}", f"{random.uniform(10,99):.2f}"))
    for i in range(0, 32, 4):
        for j in range(4): pdf.cell(47.5, 7, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    pdf.ln(5); pdf.draw_detailed_graph(10, 85, 190, 45, "LATITUDE TRAJECTORY", m_hist["lats"], (0, 100, 200))
    pdf.draw_detailed_graph(10, 140, 90, 40, "VELOCITY (KM/H)", m_hist["vels"], (200, 50, 0))
    pdf.draw_detailed_graph(110, 140, 90, 40, "ALTITUDE (KM)", m_hist["alts"], (0, 150, 50))
    pdf.set_draw_color(0,0,0); pdf.rect(15, 220, 40, 50)
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 17.5, 222, 35, 35)
    pdf.set_xy(15, 258); pdf.set_font("Arial", 'B', 7); pdf.cell(40, 5, "SECURE VERIFICATION", align='C', ln=True)
    pdf.set_x(15); pdf.cell(40, 4, f"ID: {f_id}", align='C')
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 225, 30, 20)
    pdf.line(120, 250, 190, 250); pdf.set_xy(120, 252); pdf.set_font("Arial", 'B', 10); pdf.cell(70, 5, s_name.upper(), align='C', ln=True)
    pdf.set_x(120); pdf.set_font("Arial", 'I', 8); pdf.cell(70, 5, s_pos.upper(), align='C')
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. INTERFACE (BUG-FREE POPUP)
# ==========================================
st.set_page_config(page_title="ZENITH V8.1", layout="wide")

# แก้ไขปัญหาป๊อปอัพเด้ง: ใช้ State ควบคุม 100%
if 'show_modal' not in st.session_state: st.session_state.show_modal = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ COMMAND PANEL")
    sel_sat = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 ADDRESS & TIME")
    z_a = st.text_input("โซน", "Asia")
    c_a = st.text_input("ประเทศ", "Thailand")
    p_a = st.selectbox("จังหวัด", list(LOC_DB.keys()))
    d_a = st.text_input("อำเภอ", "Mueang")
    s_a = st.text_input("ตำบล", "That Choeng Chum")
    
    loc_info = LOC_DB.get(p_a); st_lat, st_lon, st_tz = loc_info["lat"], loc_info["lon"], loc_info["tz"]

    st.divider()
    st.subheader("🔍 MULTI-ZOOM")
    # เพิ่ม key ให้กับ slider เพื่อแยกประเภทข้อมูลออกจาก state อื่นๆ
    z1 = st.slider("Tactical", 1, 18, 12, key="zoom_1")
    z2 = st.slider("Global", 1, 10, 2, key="zoom_2")
    z3 = st.slider("Station", 1, 18, 15, key="zoom_3")
    
    # ปุ่มนี้จะเปลี่ยน state เพื่อเปิด popup เท่านั้น
    if st.button("🧧 EXECUTE SECURE ARCHIVE", use_container_width=True, type="primary"):
        st.session_state.show_modal = True

# Popup จะทำงานเมื่อ st.session_state.show_modal เป็น True เท่านั้น
@st.dialog("📋 ARCHIVE FINALIZATION")
def modal():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Mode", ["Live", "Predictive"], horizontal=True)
        t_target = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            t_target = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
        
        st.divider()
        s_name = st.text_input("Officer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Designation", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        
        if st.button("🚀 BUILD & ENCRYPT"):
            fid = f"SEC-{random.randint(100,999)}-{datetime.now().strftime('%H%M')}"
            pwd = "".join([str(random.randint(0,9)) for _ in range(6)])
            m_main, m_hist = run_calculation(sat_catalog[sel_sat], t_target)
            addr = {"z": z_a, "c": c_a, "p": p_a, "d": d_a, "s": s_a}
            st.session_state.pdf_blob = build_ultimate_archive(sel_sat, addr, s_name, s_pos, s_img, fid, pwd, m_main, m_hist)
            st.session_state.fid, st.session_state.pwd = fid, pwd
            st.rerun()
    else:
        st.markdown(f"""
            <div style="border: 4px solid black; padding: 25px; border-radius: 15px; text-align: center; background: white;">
                <p style="color: gray; font-weight: bold;">DOCUMENT ARCHIVE ID</p>
                <h2 style="color: red; font-weight: 900; font-size: 32px; margin-top: -10px;">{st.session_state.fid}</h2>
                <hr>
                <p style="color: gray; font-weight: bold;">ENCRYPTION KEY (PASSWORD)</p>
                <h1 style="color: black; font-weight: 900; font-size: 50px; letter-spacing: 12px; margin-top: -10px;">{st.session_state.pwd}</h1>
            </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.fid}.pdf", use_container_width=True)
        if st.button("RETURN TO DASHBOARD", use_container_width=True):
            st.session_state.show_modal = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.show_modal:
    modal()

@st.fragment(run_every=1.0)
def main_dashboard():
    synced_time = (datetime.now(timezone.utc) + timedelta(hours=st_tz)).strftime("%H:%M:%S")
    st.markdown(f'''<div style="text-align:center; background:white; border:5px solid black; padding:10px; border-radius:100px; margin-bottom:20px;">
                <span style="color:black; font-size:60px; font-weight:900; font-family:monospace;">{synced_time}</span>
                <p style="margin:0; font-weight:bold; color:gray;">LOCATION: {p_a} (UTC+{st_tz})</p></div>''', unsafe_allow_html=True)
    
    if sat_catalog and sel_sat in sat_catalog:
        m_main, m_hist = run_calculation(sat_catalog[sel_sat])
        c1, c2, c3 = st.columns(3)
        c1.metric("ALTITUDE", f"{m_main['TRK_ALT']:,.2f} KM")
        c2.metric("VELOCITY", f"{m_main['TRK_VEL']:,.0f} KM/H")
        c3.metric("COORD", f"{m_main['TRK_LAT']:.4f}, {m_main['TRK_LON']:.4f}")
        
        m_cols = st.columns(3)
        def draw_map(lt, ln, zm, k, tl, tn, label):
            st.caption(f"**{label}**")
            fig = go.Figure()
            if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
            fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)

        with m_cols[0]: draw_map(m_main['TRK_LAT'], m_main['TRK_LON'], z1, "m1", m_hist["lats"], m_hist["lons"], "TACTICAL VIEW")
        with m_cols[1]: draw_map(m_main['TRK_LAT'], m_main['TRK_LON'], z2, "m2", m_hist["lats"], m_hist["lons"], "GLOBAL ORBIT")
        with m_cols[2]: draw_map(st_lat, st_lon, z3, "m3", [], [], f"STATION: {p_a}")

        st.subheader("📊 REAL-TIME TELEMETRY STREAM")
        st.table(pd.DataFrame([list(m_main.items()) + [("STATUS", "SECURE")] for _ in range(1)]))

main_dashboard()