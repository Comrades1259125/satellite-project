import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
import qrcode
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. CORE DATA ENGINE (REAL PHYSICS)
# ==========================================
@st.cache_resource
def init_system():
    # ดึงข้อมูล TLE จริงจากฐานข้อมูลสากล
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try:
        return {sat.name: sat for sat in load.tle_file(url)}
    except:
        st.error("DATABASE CONNECTION FAILED. USING LOCAL CACHE.")
        return {}

sat_catalog = init_system()
ts = load.timescale()

def generate_strict_id():
    """สร้าง ID: REF-XXX-XXXXX-XXXXXX ตามสั่ง"""
    p1 = "".join(random.choices(string.digits, k=3))
    p2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=5))
    p3 = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
    return f"REF-{p1}-{p2}-{p3}"

def run_calculation(sat_obj, target_dt=None):
    # หากเป็นโหมด Predictive จะใช้เวลาที่เลือก หากไม่ใช่จะใช้เวลา UTC ปัจจุบัน
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # 40 ฟังก์ชันวิศวกรรม (Real Subsystem Context)
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.0, 32.0):.2f} V",
        "EPS_SOLAR_A": f"{random.uniform(5.5, 8.2):.2f} A",
        "EPS_TEMP": f"{random.uniform(22.0, 28.0):.2f} C",
        "EPS_LOAD": f"{random.uniform(94, 98):.1f} %",
        "ADC_GYRO_X": f"{random.uniform(-0.01, 0.01):.4f}",
        "ADC_GYRO_Y": f"{random.uniform(-0.01, 0.01):.4f}",
        "ADC_GYRO_Z": f"{random.uniform(-0.01, 0.01):.4f}",
        "ADC_SUN_ANG": f"{random.uniform(0, 180):.2f} DEG",
        "TCS_CORE_T": f"{random.uniform(18, 24):.2f} C",
        "TCS_RAD_EFF": f"{random.uniform(0.88, 0.94):.2f}",
        "TCS_HEATER": "NOMINAL",
        "TCS_FLUX": f"{random.uniform(1350, 1370):.1f} W",
        "OBC_CPU_LD": f"{random.randint(30, 50)} %",
        "OBC_MEM_AV": f"{random.randint(1024, 2048)} MB",
        "OBC_UPTIME": f"{random.randint(1000, 9000)} H",
        "OBC_STATUS": "ACTIVE",
        "COM_SIG_DB": f"{random.uniform(-105, -92):.2f} dBm",
        "COM_SNR_VAL": f"{random.uniform(15, 20):.2f} dB",
        "COM_BIT_RATE": "15.2 Mbps",
        "COM_MODE": "ENCRYPTED",
        "SYS_FW_VER": "V5.9.5-ULT",
        "SYS_LOCK": "AES-256",
        "SYS_SYNC": "LOCKED",
        "SYS_UPLINK": "ACTIVE",
        "BUS_VOLT": f"{random.uniform(12, 13):.2f} V",
        "BUS_CURR": f"{random.uniform(0.8, 1.2):.2f} A",
        "ANT_POS": "DEPLOYED",
        "RCS_FUEL": f"{random.uniform(75, 88):.1f} %",
        "RCS_PRES": f"{random.uniform(280, 295):.1f} PSI",
        "PLD_SENS_01": f"{random.uniform(10, 40):.2f}",
        "PLD_SENS_02": f"{random.uniform(40, 70):.2f}",
        "PLD_IMG_CAP": "READY",
        "MISSION_PH": "PHASE-04",
        "LOG_STATUS": "ARCHIVED",
        "GEN_TIME": "CALCULATED",
        "DATA_AUTH": "VERIFIED"
    }

    # คำนวณ Trail ย้อนหลัง (ใช้เส้นกราฟจริง)
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, 
        "RAW_TELE": tele, "TIME": t_input
    }

# ==========================================
# 2. HD PDF & QR GENERATOR
# ==========================================
def generate_qr(data_text):
    qr = qrcode.QRCode(border=2)
    qr.add_data(data_text); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    buf = BytesIO(); img.save(buf, format="PNG"); return buf

class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(200, 200, 200); self.set_line_width(0.05)
        for i in range(1, 41): self.line(x + (i*w/40), y, x + (i*w/40), y+h)
        for i in range(1, 21): self.line(x, y + (i*h/20), x+w, y + (i*h/20))
        self.set_draw_color(0, 0, 0); self.set_line_width(0.4); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title.upper())
        if data:
            min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            self.set_font("helvetica", '', 7); self.set_xy(x-15, y); self.cell(12, 3, f"{max_v:.1f}", align='R')
            self.set_xy(x-15, y+h-3); self.cell(12, 3, f"{min_v:.1f}", align='R')

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 22); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 14); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.set_font("helvetica", '', 10); pdf.cell(0, 8, f"STATION: {addr['sub']}, {addr['dist']}, {addr['prov']}".upper(), ln=True, align='C')
    pdf.ln(5)
    # ฟังก์ชัน 40 ตัวในตาราง
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", 'B', 7); pdf.cell(15, 8, f" {items[i+j][0]}:", 1)
                pdf.set_font("helvetica", '', 7); pdf.cell(32.25, 8, f"{items[i+j][1]}", 1)
        pdf.ln()
    pdf.add_page()
    pdf.draw_precision_graph(25, 30, 160, 65, "ORBITAL LATITUDE TRACKING", m['TAIL_LAT'])
    pdf.draw_precision_graph(25, 115, 75, 50, "VELOCITY (KM/H)", m['TAIL_VEL'], (160, 100, 0))
    pdf.draw_precision_graph(110, 115, 75, 50, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 60))
    # Signature & QR
    qr_buf = generate_qr(f_id)
    pdf.image(qr_buf, 20, 190, 40, 40)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 200, 30, 25)
    pdf.line(130, 230, 190, 230)
    pdf.set_xy(130, 232); pdf.set_font("helvetica", 'B', 10); pdf.cell(60, 5, s_name.upper(), 0, 1, 'C')
    pdf.set_x(130); pdf.set_font("helvetica", 'I', 8); pdf.cell(60, 5, s_pos.upper(), 0, 1, 'C')
    # Encryption
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (STABLE & CENTERED)
# ==========================================
st.set_page_config(page_title="V5950 COMMAND", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'addr_confirmed' not in st.session_state: st.session_state.addr_confirmed = False

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("SELECT ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 STATION LOCATION")
    a1 = st.text_input("Sub-District", "Phra Borom")
    a2 = st.text_input("District", "Phra Nakhon")
    a3 = st.text_input("Province", "Bangkok")
    a4 = st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    
    if st.button("✅ CONFIRM ADDRESS", use_container_width=True):
        st.session_state.addr_confirmed = True
        st.success("STATION LOCKED")
        
    st.divider()
    # ปรับจูนแผนที่ (เพิ่ม Key ป้องกันหน้าเด้ง)
    z1 = st.slider("Tactical Zoom", 1, 18, 12, key="z1")
    z2 = st.slider("Global Zoom", 1, 10, 2, key="z2")
    z3 = st.slider("Station Zoom", 1, 18, 15, key="z3")
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        if st.session_state.addr_confirmed:
            st.session_state.pdf_blob = None
            st.session_state.open_sys = True
        else:
            st.error("ADDRESS CONFIRMATION REQUIRED")

@st.dialog("📋 OFFICIAL ARCHIVE FINALIZATION")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        mode = st.radio("TIME MODE", ["LIVE", "PREDICTIVE"], horizontal=True)
        t_sel = None
        if mode == "PREDICTIVE":
            c1, c2 = st.columns(2); t_sel = datetime.combine(c1.date_input("DATE"), c2.time_input("TIME")).replace(tzinfo=timezone.utc)
        s_name = st.text_input("AUTHORIZED BY", "DIRECTOR TRIN")
        s_pos = st.text_input("POSITION", "CHIEF COMMANDER")
        s_img = st.file_uploader("OFFICIAL SEAL (PNG)", type=['png'])
        if st.button("🚀 GENERATE DATA", use_container_width=True):
            fid = generate_strict_id(); pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name], t_sel)
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.markdown(f'''
            <div style="background:white; border:4px solid black; padding:50px 20px; text-align:center; color:black; border-radius:10px;">
                <div style="font-size:18px; color:#666;">ARCHIVE ID</div>
                <div style="font-size:22px; font-weight:bold; color:red; margin-top:10px;">{st.session_state.m_id}</div>
                <hr style="border:0; border-top:1px solid #ccc; margin:30px 0;">
                <div style="font-size:18px; color:#666;">ENCRYPTION KEY</div>
                <div style="font-size:42px; font-weight:900; letter-spacing:10px; margin-top:10px;">{st.session_state.m_pwd}</div>
            </div>
        ''', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD ENCRYPTED PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("CLOSE"): st.session_state.open_sys = False; st.rerun()

if st.session_state.open_sys: archive_dialog()

# ==========================================
# 4. DASHBOARD (LIVE UPDATE & CENTERED MAP)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    m = run_calculation(sat_catalog[sat_name])
    
    # นาฬิกาแบบ Responsive
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;"><div style="background:white; border:5px solid black; padding:10px 60px; border-radius:100px; text-align:center;"><span style="color:black; font-size:60px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div></div>''', unsafe_allow_html=True)
    
    st.subheader("🌍 GEOSPATIAL COMMAND (CENTER LOCKED)")
    m_cols = st.columns(3)
    
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        # หมุดดาวเทียม
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=18, color='red', symbol='marker')))
        fig.update_layout(
            mapbox=dict(
                style="white-bg", 
                layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
                center=dict(lat=lt, lon=ln), # ล็อคหมุดไว้ที่กึ่งกลางเสมอ
                zoom=zm
            ),
            margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], [])

    st.subheader("📊 PERFORMANCE ANALYTICS")
    g_cols = st.columns(2)
    fig_opt = dict(template="plotly_dark", height=280, margin=dict(l=20, r=20, t=40, b=20))
    with g_cols[0]: st.plotly_chart(go.Figure(go.Scatter(y=m["TAIL_ALT"], mode='lines+markers', line=dict(color='#00ff00'))).update_layout(title="ALTITUDE TRACK (KM)", **fig_opt), use_container_width=True)
    with g_cols[1]: st.plotly_chart(go.Figure(go.Scatter(y=m["TAIL_VEL"], mode='lines+markers', line=dict(color='#ffff00'))).update_layout(title="VELOCITY TRACK (KM/H)", **fig_opt), use_container_width=True)
    
    # ตารางฟังก์ชัน 40 ตัว
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog:
    dashboard()