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
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. CORE DATA ENGINE
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try: return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

# Initialize Session States
if 'm_id' not in st.session_state: st.session_state.m_id = None
if 'm_pwd' not in st.session_state: st.session_state.m_pwd = None
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'station_coords' not in st.session_state: st.session_state.station_coords = [13.75, 100.5] # Default Bangkok

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # 40 UNIQUE PARAMETERS
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}", "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM", "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.0, 32.0):.2f} V", "EPS_SOLAR_A": f"{random.uniform(5.5, 8.2):.2f} A",
        "EPS_TEMP": f"{random.uniform(22, 28):.2f} C", "EPS_LOAD": f"{random.uniform(94, 98):.1f} %",
        "ADC_GYRO_X": f"{random.uniform(-0.01, 0.01):.4f}", "ADC_GYRO_Y": f"{random.uniform(-0.01, 0.01):.4f}",
        "ADC_GYRO_Z": f"{random.uniform(-0.01, 0.01):.4f}", "ADC_SUN_ANG": f"{random.uniform(0, 180):.2f} DEG",
        "TCS_CORE_T": f"{random.uniform(18, 24):.2f} C", "TCS_RAD_EFF": f"{random.uniform(0.88, 0.94):.2f}",
        "TCS_HEATER": "NOMINAL", "TCS_FLUX": f"{random.uniform(1350, 1370):.1f} W",
        "OBC_CPU_LD": f"{random.randint(30, 50)} %", "OBC_MEM_AV": f"{random.randint(1024, 2048)} MB",
        "OBC_UPTIME": f"{random.randint(1000, 9000)} H", "OBC_STATUS": "ACTIVE",
        "COM_SIG_DB": f"{random.uniform(-105, -92):.2f} dBm", "COM_SNR_VAL": f"{random.uniform(15, 20):.2f} dB",
        "COM_BIT_RATE": "15.2 Mbps", "COM_MODE": "ENCRYPTED",
        "PLD_SENS_01": f"{random.uniform(10, 40):.2f}", "PLD_SENS_02": f"{random.uniform(40, 70):.2f}",
        "PLD_IMG_CAP": "READY", "PLD_DATA_QL": "100%", "SYS_FW_VER": "V5.9.5-ULT",
        "SYS_LOCK": "AES-RSA", "SYS_SYNC": "LOCKED", "SYS_UPLINK": "ACTIVE",
        "BUS_VOLT": f"{random.uniform(12, 13):.2f} V", "BUS_CURR": f"{random.uniform(0.8, 1.2):.2f} A",
        "ANT_POS": "DEPLOYED", "RCS_FUEL": f"{random.uniform(75, 88):.1f} %",
        "RCS_PRES": f"{random.uniform(280, 295):.1f} PSI", "MISSION_PH": "PHASE-04",
        "LOG_STATUS": "ARCHIVED", "GEN_TIME": "REAL-TIME"
    }

    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, "RAW_TELE": tele}

# ==========================================
# 2. HD PDF & QR ENGINE
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.3); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 9); self.set_xy(x, y-5); self.cell(w, 5, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.5)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 22); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.ln(5)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.25, 8, f" {items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    pdf.add_page()
    pdf.draw_precision_graph(25, 30, 160, 60, "ORBITAL LATITUDE TRACKING (DEG)", m['TAIL_LAT'])
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. INTERFACE & SIDEBAR
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
    st.divider()
    st.subheader("📍 STATION LOCATION")
    sub_d = st.text_input("Sub-District", "That Choeng Chum")
    dist = st.text_input("District", "Mueang Sakon Nakhon")
    prov = st.text_input("Province", "Sakon Nakhon")
    
    # ✅ ปุ่มยืนยันที่อยู่
    if st.button("✅ ยืนยันพิกัดสถานี (CONFIRM LOCATION)", use_container_width=True):
        if "Sakon" in prov: st.session_state.station_coords = [17.16, 104.14]
        else: st.session_state.station_coords = [13.75, 100.5]
        st.success(f"STATION LOCKED: {dist}")

    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"): st.session_state.open_sys = True

# ==========================================
# 4. FIXED DIALOG (NO MORE ATTRIBUTE ERROR)
# ==========================================
if st.session_state.open_sys:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_dialog():
        if st.session_state.pdf_blob is None:
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Position", "CHIEF COMMANDER")
            s_img = st.file_uploader("Seal (PNG)", type=['png'])
            if st.button("🚀 INITIATE ENCRYPTION", use_container_width=True):
                st.session_state.m_id = f"REF-{random.randint(100, 999)}"
                st.session_state.m_pwd = ''.join(random.choices(string.digits, k=6))
                m_data = run_calculation(sat_catalog[sat_name])
                st.session_state.pdf_blob = build_pdf(sat_name, {"sub":sub_d,"dist":dist,"prov":prov}, s_name, s_pos, s_img, st.session_state.m_id, st.session_state.m_pwd, m_data)
                st.rerun()
        else:
            # ใช้ค่าจาก session_state ที่มั่นใจว่ามีอยู่จริง
            mid = st.session_state.m_id
            pwd = st.session_state.m_pwd
            st.markdown(f'''
                <div style="background:white; border:4px solid red; padding:20px; text-align:center; color:black;">
                    ID: <h2 style="color:red; margin:0;">{mid}</h2>
                    PASSKEY: <h1 style="letter-spacing:5px; margin:0;">{pwd}</h1>
                </div>
            ''', unsafe_allow_html=True)
            st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{mid}.pdf", use_container_width=True)
            if st.button("CLOSE"):
                st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()
    archive_dialog()

# ==========================================
# 5. DASHBOARD
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;"><div style="background:white; border:5px solid black; padding:10px 60px; border-radius:100px; text-align:center;"><span style="color:black; font-size:60px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div></div>''', unsafe_allow_html=True)
    
    m = run_calculation(sat_catalog[sat_name])
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT_VAL']:.2f} KM")
    c2.metric("VELOCITY", f"{m['VEL_VAL']:.2f} KM/H")
    c3.metric("GPS", f"{m['LAT']:.3f}, {m['LON']:.3f}")

    # MAPS
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, tl, tn, color='red'):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=f"{k}_{lt}")

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(st.session_state.station_coords[0], st.session_state.station_coords[1], z3, "S", [], [], 'blue')

    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()