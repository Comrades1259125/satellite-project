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

# --- 1. UNIQUE TELEMETRY PARAMETERS (40 FUNCTIONS) ---
LABELS = [
    "LATITUDE", "LONGITUDE", "ALTITUDE", "VELOCITY", "NORAD_ID", "INCLIN", "PERIOD", "ECCENT", "DRAG", "STATUS",
    "BAT_V", "BAT_T", "SOL_A", "SOL_B", "BUS_C", "RW_X", "RW_Y", "RW_Z", "GYRO", "MAG_I",
    "CPU_L", "MEM_F", "OS_ST", "UL_SIG", "DL_BW", "THERM", "CORE_T", "ANT_A", "S_BAND", "X_BAND",
    "OBC_H", "EPS_C", "TTC_D", "ADCS", "AOCS", "PROP_T", "FUEL_L", "THRUST", "PLD_A", "MISSION"
]

@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t); subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    vals = [f"{subpoint.latitude.degrees:.4f}", f"{subpoint.longitude.degrees:.4f}", 
            f"{subpoint.elevation.km:.2f}", f"{v_km_s * 3600:.1f}", "25544", "51.6", "92.8", "0.0008", "0.0002", "ACTIVE"]
    for _ in range(30): vals.append(f"{random.uniform(10, 99):.1f}")
    
    matrix = [f"{l}: {v}" for l, v in zip(LABELS, vals)]
    history = {"lats": [], "lons": [], "vels": [], "alts": []}
    for i in range(0, 21, 2):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); s = wgs84.subpoint(g)
        history["lats"].append(s.latitude.degrees); history["lons"].append(s.longitude.degrees)
        history["vels"].append(np.linalg.norm(g.velocity.km_per_s) * 3600)
        history["alts"].append(s.elevation.km)
    return matrix, history, subpoint.latitude.degrees, subpoint.longitude.degrees

# --- 2. PDF ENGINE ---
class ULTIMATE_PDF(FPDF):
    def draw_grid_graph(self, x, y, w, h, title, data, color):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(200, 200, 200); self.set_line_width(0.1)
        for i in range(11): lx = x + (i * (w / 10)); self.line(lx, y, lx, y + h)
        for i in range(6): ly = y + (i * (h / 5)); self.line(x, ly, x + w, ly)
        min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
        pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
        self.set_draw_color(*color); self.set_line_width(0.5)
        for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m_main, m_hist):
    pdf = ULTIMATE_PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, f"DATA REPORT: {sat_name}", ln=True, align='C')
    pdf.set_font("Courier", 'B', 7)
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(m_main): pdf.cell(47.5, 8, m_main[i+j], border=1)
        pdf.ln()
    pdf.add_page()
    pdf.draw_grid_graph(20, 40, 170, 45, "LAT", m_hist["lats"], (0, 102, 204))
    pdf.draw_grid_graph(20, 105, 170, 45, "VEL", m_hist["vels"], (204, 0, 0))
    pdf.draw_grid_graph(20, 170, 170, 45, "ALT", m_hist["alts"], (0, 153, 51))
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 15, 240, 30, 30)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 150, 240, 30, 20)
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter(); 
    for p in reader.pages: writer.add_page(p); writer.encrypt(pwd)
    out = BytesIO(); writer.write(out); return out.getvalue()

# --- 3. DASHBOARD UI ---
st.set_page_config(page_title="ZENITH V9.4", layout="wide")
if "archive" not in st.session_state: st.session_state.archive = None
if "show_modal" not in st.session_state: st.session_state.show_modal = False

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()))
    p_a = st.text_input("Province", "Sakon Nakhon Province")
    d_a = st.text_input("District", "Mueang Sakon Nakhon District")
    s_a = st.text_input("Subdistrict", "That Choeng Chum Subdistrict")
    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    # Mode Predictive
    mode = st.radio("Analytics", ["Live Now", "Predictive"])
    t_target = None
    if mode == "Predictive":
        c1, c2 = st.columns(2); t_target = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
    
    # แก้ไขปุ่มให้กดแล้วป๊อปอัพขึ้นครั้งเดียว ไม่เด้งรบกวน
    if st.button("🧧 GENERATE REPORT", use_container_width=True, type="primary"):
        st.session_state.show_modal = True

# --- กู้คืนระบบป๊อปอัพดาวน์โหลดและรหัสผ่าน ---
if st.session_state.show_modal:
    @st.dialog("📋 MISSION DATA ARCHIVE")
    def modal():
        if st.session_state.archive is None:
            s_name = st.text_input("Officer Name"); s_pos = st.text_input("Designation")
            s_img = st.file_uploader("Seal (PNG)", type=['png'])
            if st.button("🚀 EXECUTE ENCRYPTION"):
                fid = f"REF-{random.randint(100,999)}"; pwd = str(random.randint(100000, 999999))
                m_main, m_hist, _, _ = run_calculation(sat_catalog[sel_sat], t_target)
                pdf = build_pdf(sel_sat, {"p":p_a, "d":d_a, "s":s_a}, s_name, s_pos, s_img, fid, pwd, m_main, m_hist)
                st.session_state.archive = {"pdf": pdf, "fid": fid, "pwd": pwd}; st.rerun()
        else:
            arc = st.session_state.archive
            st.markdown(f'<div style="border:4px solid red; padding:20px; text-align:center; background:white; color:black;">'
                        f'ARCHIVE ID: <h2 style="color:red;">{arc["fid"]}</h2>'
                        f'PASSKEY: <h1 style="letter-spacing:10px;">{arc["pwd"]}</h1></div>', unsafe_allow_html=True)
            st.download_button("📥 DOWNLOAD ENCRYPTED PDF", arc["pdf"], f"{arc['fid']}.pdf", use_container_width=True)
            if st.button("CLOSE & RESET"): st.session_state.archive = None; st.session_state.show_modal = False; st.rerun()
    modal()

# --- หน้าจอหลัก (อัปเดตพิกัดนิ่งและนาฬิกาเห็นชัด) ---
@st.fragment(run_every=1.0)
def dashboard():
    m_main, m_hist, cur_lat, cur_lon = run_calculation(sat_catalog[sel_sat])
    
    # นาฬิกาแบบเห็นชัดในทุกโหมด (ใส่พื้นหลังสีขาวตัวหนังสือดำเสมอ)
    st.markdown(f'''
        <div style="text-align:center; background:white; border:5px solid black; border-radius:100px; padding:10px; margin-bottom:15px;">
            <span style="font-size:clamp(40px, 10vw, 70px); font-weight:900; color:black; font-family:monospace;">
                {datetime.now().strftime("%H:%M:%S")}
            </span>
        </div>
    ''', unsafe_allow_html=True)

    # แผนที่ 3 ชุด (จุดนิ่งตามดาวเทียมจริง)
    c_m = st.columns(3)
    map_configs = [
        (cur_lat, cur_lon, z1, "TACTICAL", "red"),
        (cur_lat, cur_lon, z2, "GLOBAL", "red"),
        (17.16, 104.14, z3, "STATION", "blue")
    ]
    for i, (la, lo, zm, tit, col) in enumerate(map_configs):
        with c_m[i]:
            st.caption(f"**{tit}**")
            fig = go.Figure(go.Scattermapbox(lat=[la], lon=[lo], mode='markers', marker=dict(size=15, color=col)))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=la, lon=lo), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=300)
            st.plotly_chart(fig, use_container_width=True, key=f"map_{i}")

    # กราฟ (อัปเดตจริง)
    c_g = st.columns(2)
    with c_g[0]:
        st.caption("**VELOCITY TREND**")
        st.line_chart(m_hist["vels"], height=150)
    with c_g[1]:
        st.caption("**ALTITUDE TREND**")
        st.line_chart(m_hist["alts"], height=150)
    
    # ตาราง 40 รายการ (ไม่ซ้ำ)
    st.table(pd.DataFrame([m_main[i:i+4] for i in range(0, 40, 4)]))

dashboard()