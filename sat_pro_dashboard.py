import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84
import random
import string

# ==========================================
# 1. CORE ENGINE (REAL DATA & ID GENERATOR)
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try: return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

def generate_strict_id():
    """สร้าง ID ในรูปแบบ REF-123-12SG6-12356S โดยสุ่มค่าแต่ล็อคตำแหน่ง"""
    part1 = "".join(random.choices(string.digits, k=3))
    part2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=5))
    part3 = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
    return f"REF-{part1}-{part2}-{part3}"

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # 40 ฟังก์ชันชื่อวิศวกรรมจริง (Real Subsystems)
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": "28.42 V", "EPS_SOLAR_A": "5.21 A", "EPS_TEMP": "24.50 C", "EPS_MODE": "CHARGING",
        "ADCS_GYRO_X": "0.0012", "ADCS_GYRO_Y": "-0.0045", "ADCS_GYRO_Z": "0.0021", "ADCS_SUN_ANG": "42.15 DEG",
        "OBC_CPU_LOAD": "34.2 %", "OBC_MEM_FREE": "1024 MB", "OBC_UPTIME": "4521.5 H", "OBC_TEMP": "31.20 C",
        "TCS_HEATER": "OFF", "TCS_RAD_TEMP": "-12.40 C", "TCS_INTERNAL": "22.15 C", "TCS_FLUX": "1361 W/m2",
        "COM_RSSI": "-98.4 dBm", "COM_SNR": "18.5 dB", "COM_BITRATE": "15.2 Mbps", "COM_FREQ": "2245.5 MHz",
        "PLD_POWER": "120.4 W", "PLD_TEMP": "18.50 C", "PLD_DATA_BUF": "88 %", "PLD_STATUS": "OPERATIONAL",
        "RCS_FUEL": "78.2 %", "RCS_PRESS": "245.2 PSI", "RCS_THRUST": "NOMINAL", "ANT_STAT": "DEPLOYED",
        "BUS_V": "12.05 V", "BUS_A": "0.85 A", "GPS_LOCK": "FIXED", "GPS_SATS": "12",
        "SYS_HEALTH": "100%", "SYS_WDG": "ENABLED", "PHASE": "OPERATIONAL", "LOG": "ACTIVE"
    }

    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, "RAW_TELE": tele}

# ==========================================
# 2. PDF ENGINE (GRID & SCALES)
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(200, 200, 200); self.set_line_width(0.05)
        for i in range(0, 11): lx = x + (i * w / 10); self.line(lx, y, lx, y + h)
        for i in range(0, 6): ly = y + (i * h / 5); self.line(x, ly, x + w, ly)
        self.set_draw_color(0, 0, 0); self.set_line_width(0.3); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 9); self.set_xy(x, y - 4); self.cell(w, 4, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
            self.set_font("helvetica", '', 6); self.set_xy(x - 12, y); self.cell(10, 3, f"{max_v:.1f}", align='R')
            self.set_xy(x - 12, y + h - 3); self.cell(10, 3, f"{min_v:.1f}", align='R')
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.5)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 22); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 14); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.ln(5)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", 'B', 7); pdf.cell(15, 8, f" {items[i+j][0]}:", border='LTB')
                pdf.set_font("helvetica", '', 7); pdf.cell(32.25, 8, f"{items[i+j][1]}", border='RTB')
        pdf.ln()
    pdf.add_page()
    pdf.draw_precision_graph(20, 30, 170, 60, "ORBITAL LATITUDE TRACKING", m['TAIL_LAT'])
    pdf.draw_precision_graph(20, 110, 80, 45, "VELOCITY (KM/H)", m['TAIL_VEL'], (160, 100, 0))
    pdf.draw_precision_graph(110, 110, 80, 45, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 60))
    pdf.line(110, 245, 190, 245)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 140, 215, 30, 25)
    pdf.set_xy(110, 247); pdf.set_font("helvetica", 'B', 11); pdf.cell(80, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("helvetica", 'I', 9); pdf.cell(80, 5, s_pos.upper(), align='C')
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter(); writer.add_page(reader.pages[0]); writer.add_page(reader.pages[1])
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (POPUP & ZOOM PROTECTION)
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

# ล็อค State ป้องกันป๊อปอัพเด้ง
if 'show_modal' not in st.session_state: st.session_state.show_modal = False
if 'pdf_ready' not in st.session_state: st.session_state.pdf_ready = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()) if sat_catalog else ["LOADING..."])
    a1, a2, a3, a4 = st.text_input("Sub-District", "Phra Borom"), st.text_input("District", "Phra Nakhon"), st.text_input("Province", "Bangkok"), st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    # ปุ่มกดครั้งเดียวเพื่อเปิดหน้าต่าง
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.pdf_ready = None
        st.session_state.show_modal = True

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_ready is None:
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        if st.button("🚀 INITIATE", use_container_width=True):
            # สุ่มเลข/อักษร แต่ล็อคตำแหน่งเดิมเป๊ะๆ
            fid = generate_strict_id() 
            pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name])
            st.session_state.pdf_ready = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        # กรอบขาวสูง + เส้นขีดคั่นกลาง
        st.markdown(f'''
            <div style="background:white; border:4px solid black; padding:50px 20px; text-align:center; color:black; border-radius:10px;">
                <div style="font-size:18px; color:#666;">DOCUMENT ARCHIVE ID</div>
                <div style="font-size:24px; font-weight:bold; color:red; margin-top:10px;">{st.session_state.m_id}</div>
                <hr style="border:0; border-top:1px solid #ccc; margin:30px 0;">
                <div style="font-size:18px; color:#666;">ENCRYPTION KEY</div>
                <div style="font-size:42px; font-weight:900; letter-spacing:10px; margin-top:10px;">{st.session_state.m_pwd}</div>
            </div>
        ''', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD ENCRYPTED ARCHIVE", st.session_state.pdf_ready, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("RETURN TO COMMAND"): 
            st.session_state.show_modal = False
            st.session_state.pdf_ready = None
            st.rerun()

# จุดเช็คสถานะป๊อปอัพ (ย้ายมาไว้นอก Sidebar เพื่อป้องกันการ Rerun จาก Slider)
if st.session_state.show_modal:
    archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;"><div style="background:white; border:5px solid black; padding:10px 60px; border-radius:100px; text-align:center;"><span style="color:black; font-size:60px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div></div>''', unsafe_allow_html=True)
    m = run_calculation(sat_catalog[sat_name])
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, tl=[], tn=[]):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=14, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)
    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(13.75, 100.5, z3, "S1")
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()