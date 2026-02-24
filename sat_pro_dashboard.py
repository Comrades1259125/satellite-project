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

# --- 1. ปรับปรุงพารามิเตอร์ 40 รายการให้ไม่ซ้ำกัน (Unique Functions) ---
# ผสมผสานข้อมูลจริงและระบบจำลองเพื่อความหลากหลาย
CORE_METRICS = ["LATITUDE", "LONGITUDE", "ALTITUDE", "VELOCITY", "NORAD_ID", "INCLINATION", "PERIOD", "ECCENTRICITY", "BSTAR_DRAG", "MISSION_ST"]
SYS_METRICS = [
    "BAT_VOLT", "BAT_TEMP", "SOL_PWR_A", "SOL_PWR_B", "BUS_CURR", "RW_X_RPM", "RW_Y_RPM", "RW_Z_RPM", 
    "GYRO_STAB", "MAG_INTEN", "CPU_LOAD", "MEM_FREE", "OS_STATUS", "UL_SIGNAL", "DL_BANDW", "THERM_SHLD", 
    "CORE_TEMP", "ANT_ALIGN", "S_BAND_ACT", "X_BAND_HZ", "OBC_HEALTH", "EPS_CONV", "TTC_DELAY", "ADCS_ERR", 
    "AOCS_SYNC", "PROP_TANK", "FUEL_LVL", "THRUST_A", "THRUST_B", "PLD_ACTIVE"
]
ALL_PARAMS = CORE_METRICS + SYS_METRICS # รวมเป็น 40 รายการที่ไม่ซ้ำกัน

@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

# --- 2. ฐานข้อมูลที่อยู่ชื่อเต็ม (Full Name Search) ---
LOC_DB = {
    "Sakon Nakhon": {
        "lat": 17.1612, "lon": 104.1486, "tz": 7,
        "full_p": "Sakon Nakhon Province",
        "full_d": "Mueang Sakon Nakhon District",
        "full_s": "That Choeng Chum Subdistrict"
    },
    "Bangkok": {
        "lat": 13.7563, "lon": 100.5018, "tz": 7,
        "full_p": "Bangkok Metropolis",
        "full_d": "Pathum Wan District",
        "full_s": "Rong Muang Subdistrict"
    }
}

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t); subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # สร้างข้อมูล Matrix 40 ช่อง
    vals = [
        f"{subpoint.latitude.degrees:.5f}°", f"{subpoint.longitude.degrees:.5f}°",
        f"{subpoint.elevation.km:.2f} KM", f"{v_km_s * 3600:.1f} KM/H",
        "25544", "51.6321°", "92.85 MIN", "0.000852", "0.000205", "NOMINAL"
    ]
    # เติมส่วนที่เหลือด้วยค่าสุ่มที่ดูสมจริง
    for _ in range(30): vals.append(f"{random.uniform(10, 99):.2f} units")
    
    matrix_data = [f"{label}: {val}" for label, val in zip(ALL_PARAMS, vals)]
    
    history = {"lats": [], "lons": [], "vels": [], "alts": []}
    for i in range(0, 61, 5):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); s = wgs84.subpoint(g)
        history["lats"].append(s.latitude.degrees); history["lons"].append(s.longitude.degrees)
        history["vels"].append(np.linalg.norm(g.velocity.km_per_s) * 3600)
        history["alts"].append(s.elevation.km)
    return matrix_data, history

class ULTIMATE_PDF(FPDF):
    def draw_grid_graph(self, x, y, w, h, title, data, color, unit):
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
    pdf.add_page()
    # หน้า 1: รายงานหลัก
    pdf.set_font("Arial", 'B', 18); pdf.cell(0, 10, f"OFFICIAL MISSION DATA REPORT: {sat_name.upper()}", ln=True, align='C')
    pdf.set_font("Arial", '', 10); gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.cell(0, 8, f"REPORT GENERATED: {gen_time} | MODE: Live Now", ln=True, align='C')
    
    pdf.ln(5); pdf.set_fill_color(230); pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, " GROUND STATION IDENTIFICATION", ln=True, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Location: {addr['s']}, {addr['d']}, {addr['p']}, {addr['c']}", ln=True)

    pdf.ln(2); pdf.set_font("Arial", 'B', 11); pdf.cell(0, 8, " TECHNICAL TELEMETRY MATRIX", ln=True, fill=True)
    pdf.set_font("Courier", 'B', 7)
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(m_main): pdf.cell(47.5, 7, m_main[i+j].upper(), border=1)
        pdf.ln()

    # หน้า 2: กราฟละเอียด
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "PRECISION ANALYTICS - PAGE 2", ln=True, align='C')
    pdf.draw_grid_graph(20, 40, 170, 45, "LATITUDE", m_hist["lats"], (0, 102, 204), "DEG")
    pdf.draw_grid_graph(20, 105, 170, 45, "VELOCITY", m_hist["vels"], (204, 0, 0), "KM/H")
    pdf.draw_grid_graph(20, 170, 170, 45, "ALTITUDE", m_hist["alts"], (0, 153, 51), "KM")
    
    # ลายเซ็นและ QR
    pdf.set_draw_color(0); pdf.rect(15, 235, 40, 45)
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 17.5, 237, 35, 35)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 235, 30, 20)
    pdf.line(120, 265, 190, 265); pdf.set_xy(120, 267); pdf.set_font("Arial", 'B', 10); pdf.cell(70, 5, s_name.upper() if s_name else "DIRECTOR", align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter(); 
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# --- 3. UI DASHBOARD ---
st.set_page_config(page_title="ZENITH V9.1", layout="wide")
if "archive_data" not in st.session_state: st.session_state.archive_data = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
    z_a = st.text_input("โซน", "Asia")
    c_a = st.text_input("ประเทศ", "Thailand")
    p_choice = st.selectbox("จังหวัด (Full Name Database)", list(LOC_DB.keys()))
    
    # ดึงชื่อเต็มจาก Database
    loc_ref = LOC_DB[p_choice]
    p_a = st.text_input("Province Full Name", loc_ref["full_p"])
    d_a = st.text_input("District Full Name", loc_ref["full_d"])
    s_a = st.text_input("Subdistrict Full Name", loc_ref["full_s"])
    
    st_lat, st_lon, st_tz = loc_ref["lat"], loc_ref["lon"], loc_ref["tz"]
    st.divider()
    
    if st.button("🧧 GENERATE MISSION ARCHIVE", use_container_width=True, type="primary"):
        st.session_state.gen_trigger = True

# --- ป๊อปอัพดาวน์โหลด (Fixed Persistence) ---
if st.session_state.get("gen_trigger"):
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
                st.session_state.archive_data = {"pdf": build_pdf(sel_sat, addr, s_name, s_pos, s_img, fid, pwd, m_main, m_hist), "fid": fid, "pwd": pwd}
                st.rerun()
        else:
            d = st.session_state.archive_data
            st.markdown(f'<div style="border:4px solid black; padding:20px; text-align:center; background:white; color:black;">ID: <h2 style="color:red;">{d["fid"]}</h2>PASS: <h1 style="letter-spacing:10px;">{d["pwd"]}</h1></div>', unsafe_allow_html=True)
            st.download_button("📥 DOWNLOAD PDF", d["pdf"], f"{d['fid']}.pdf", use_container_width=True)
            if st.button("CLOSE"): st.session_state.archive_data = None; st.session_state.gen_trigger = False; st.rerun()
    mission_modal()

# --- หน้าจอหลัก ---
@st.fragment(run_every=1.0)
def main_dashboard():
    # 1. นาฬิกาแคปซูล (รองรับทุกหน้าจอ)
    synced_time = (datetime.now(timezone.utc) + timedelta(hours=st_tz)).strftime("%H:%M:%S")
    st.markdown(f'''
        <div style="text-align:center; background:white; border:5px solid black; border-radius:100px; padding:10px; margin-bottom:20px; width:100%;">
            <span style="color:black; font-size:clamp(30px, 8vw, 70px); font-weight:900; font-family:monospace;">{synced_time}</span>
            <p style="margin:0; font-weight:bold; color:gray; font-size:12px;">LOCATION: {p_choice}</p>
        </div>
    ''', unsafe_allow_html=True)

    if sat_catalog and sel_sat in sat_catalog:
        m_main, m_hist = run_calculation(sat_catalog[sel_sat])
        
        # 2. ตัวเลขหลัก (Responsive Columns)
        c1, c2, c3 = st.columns(3)
        c1.metric("ALTITUDE", m_main[2].split(': ')[1])
        c2.metric("VELOCITY", m_main[3].split(': ')[1])
        c3.metric("POSITION", f"{m_main[0].split(': ')[1]}")

        # 3. แผนที่และกราฟในระบบ (Dashboard Graphs)
        col_m, col_g = st.columns([2, 1])
        with col_m:
            fig_map = go.Figure(go.Scattermapbox(lat=[m_hist["lats"][0]], lon=[m_hist["lons"][0]], mode='markers+lines', marker=dict(size=10, color='red')))
            fig_map.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=m_hist["lats"][0], lon=m_hist["lons"][0]), zoom=3), margin=dict(l=0,r=0,t=0,b=0), height=400)
            st.plotly_chart(fig_map, use_container_width=True)
        
        with col_g:
            # เพิ่มกราฟความเร็วใน Dashboard
            fig_v = go.Figure(go.Scatter(y=m_hist["vels"], mode='lines+markers', line=dict(color='red')))
            fig_v.update_layout(title="VELOCITY TREND (KM/H)", height=200, margin=dict(l=0,r=0,t=30,b=0), xaxis_visible=False)
            st.plotly_chart(fig_v, use_container_width=True)
            # กราฟความสูง
            fig_a = go.Figure(go.Scatter(y=m_hist["alts"], mode='lines+markers', line=dict(color='green')))
            fig_a.update_layout(title="ALTITUDE TREND (KM)", height=200, margin=dict(l=0,r=0,t=30,b=0), xaxis_visible=False)
            st.plotly_chart(fig_a, use_container_width=True)

        # 4. ตาราง 40 ฟังก์ชั่น (ห้ามซ้ำ)
        st.subheader("📊 UNIQUE TECHNICAL TELEMETRY MATRIX")
        df_matrix = pd.DataFrame([m_main[i:i+4] for i in range(0, 40, 4)])
        st.table(df_matrix)

main_dashboard()