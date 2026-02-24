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
from PIL import Image, ImageDraw

# ==========================================
# 1. CORE DATA ENGINE (ROBUST VERSION)
# ==========================================
@st.cache_data(ttl=3600) # รีเฟรชข้อมูลทุก 1 ชม.
def get_satellite_data():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        satellites = load.tle_file(url)
        return {sat.name: sat for sat in satellites}
    except Exception as e:
        st.error(f"🛰️ Connection Error: {e}")
        return {}

sat_catalog = get_satellite_data()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    
    # คำนวณพิกัดปัจจุบัน
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # จำลอง Telemetry (เพิ่มความสมจริงของ Logic)
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}°",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}°",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:,.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.5, 31.8):.2f} V",
        "EPS_LOAD": f"{random.uniform(92, 99):.1f} %",
        "OBC_TEMP": f"{random.uniform(20, 25):.2f} °C",
        "COM_SNR": f"{random.uniform(16, 22):.2f} dB",
        "SYS_FW": "V5.9.5-ULT",
        "SYS_LOCK": "AES-RSA-2048",
        "MISSION": "NOMINAL"
    }
    # เติมพารามิเตอร์เสริมให้ครบ 40 ช่องสำหรับตาราง
    for i in range(29):
        tele[f"DAT_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # คำนวณ Tail (ย้อนหลัง 100 นาที) แบบ Vectorized
    minutes = np.linspace(0, 100, 11)
    lats, lons, alts, vels = [], [], [], []
    for m in minutes:
        pt = ts.from_datetime(t_input - timedelta(minutes=float(m)))
        g = sat_obj.at(pt)
        ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees)
        lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km)
        vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels,
        "RAW_TELE": tele
    }

# ==========================================
# 2. HD PDF & QR ENGINE (REFACTORED)
# ==========================================
def generate_verified_qr(data_text):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # แต่ง QR ให้ดูเป็นทางการ
    w, h = img.size
    canvas = Image.new('RGB', (w + 40, h + 100), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([10, 10, w + 30, h + 90], outline="black", width=3)
    canvas.paste(img, (20, 20))
    # ใส่ข้อความกำกับท้าย QR
    draw.text((w/2 + 20, h + 55), "ENCRYPTED ARCHIVE", fill="black", anchor="mm")
    
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf

class PDF_REPORT(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color):
        self.set_fill_color(250, 250, 250); self.rect(x, y, w, h, 'F')
        self.set_draw_color(200, 200, 200); self.set_line_width(0.1)
        # ตาราง Grid
        for i in range(1, 11):
            self.line(x + (i*w/10), y, x + (i*w/10), y+h)
            self.line(x, y + (i*h/10), x+w, y + (i*h/10))
        
        self.set_draw_color(0, 0, 0); self.set_line_width(0.5); self.rect(x, y, w, h)
        self.set_font("Helvetica", 'B', 9); self.set_xy(x, y-5); self.cell(w, 5, title)
        
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.7)
            for i in range(len(pts)-1):
                self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def create_secure_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = PDF_REPORT()
    pdf.add_page()
    # Header Section
    pdf.set_font("Helvetica", 'B', 24); pdf.cell(0, 20, "MISSION CONTROL ARCHIVE", ln=True, align='C')
    pdf.set_font("Helvetica", 'B', 12); pdf.cell(0, 10, f"ID: {f_id}", ln=True, align='C')
    pdf.ln(10)
    
    # Telemetry Grid
    pdf.set_font("Helvetica", '', 7)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                key, val = items[i+j]
                pdf.cell(47, 8, f" {key}: {val}", border=1)
        pdf.ln()

    # Graphs Page
    pdf.add_page()
    pdf.draw_precision_graph(20, 30, 170, 70, "LATITUDE TRAJECTORY", m['TAIL_LAT'], (0, 102, 204))
    pdf.draw_precision_graph(20, 115, 80, 50, "VELOCITY PROFILE", m['TAIL_VEL'], (204, 102, 0))
    pdf.draw_precision_graph(110, 115, 80, 50, "ALTITUDE PROFILE", m['TAIL_ALT'], (34, 139, 34))
    
    # Footer Section (Sign & QR)
    qr_buf = generate_verified_qr(f_id)
    pdf.image(qr_buf, 20, 185, 45, 65)
    
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 140, 200, 30, 20)
    pdf.line(110, 225, 185, 225)
    pdf.set_xy(110, 227); pdf.set_font("Helvetica", 'B', 11); pdf.cell(75, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("Helvetica", 'I', 9); pdf.cell(75, 5, s_pos.upper(), align='C')

    # Encryption Logic
    raw = BytesIO(pdf.output())
    reader = PdfReader(raw); writer = PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.encrypt(pwd)
    final = BytesIO(); writer.write(final)
    return final.getvalue()

# ==========================================
# 3. RESPONSIVE UI (ULTIMATE DASHBOARD)
# ==========================================
st.set_page_config(page_title="V5950 SAT-ANALYTICS", layout="wide", initial_sidebar_state="expanded")

# Custom CSS
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background: #1a1c24; padding: 15px; border-radius: 10px; border-left: 5px solid #00ff00; }
    .clock-container { background: #ffffff; border: 4px solid #333; padding: 10px; border-radius: 50px; text-align: center; margin-bottom: 25px; }
    .clock-text { color: #000; font-size: 50px; font-weight: 900; font-family: 'Courier New', Courier, monospace; }
    @media (max-width: 600px) { .clock-text { font-size: 30px; } }
    </style>
""", unsafe_allow_html=True)

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

# Sidebar
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2554/2554032.png", width=80)
    st.title("MISSION CONTROL")
    if sat_catalog:
        selected_sat = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
        sat_obj = sat_catalog[selected_sat]
    
    with st.expander("📍 GROUND STATION"):
        a1 = st.text_input("Sub-Dist", "Phra Borom")
        a2 = st.text_input("District", "Phra Nakhon")
        a3 = st.text_input("Province", "Bangkok")
        addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": "TH"}
        
    st.divider()
    z1 = st.slider("Tactical Zoom", 1, 18, 12)
    z2 = st.slider("Global View", 1, 10, 2)
    
    if st.button("🧧 GENERATE SECURE REPORT", use_container_width=True, type="primary"):
        st.session_state.open_sys = True

# Dialog System
@st.dialog("📋 SECURE ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        col1, col2 = st.columns(2)
        mode = col1.radio("Operation Mode", ["Live", "Predictive"])
        t_sel = None
        if mode == "Predictive":
            d = col2.date_input("Target Date")
            t = col2.time_input("Target Time")
            t_sel = datetime.combine(d, t).replace(tzinfo=timezone.utc)
            
        s_name = st.text_input("Authorized Signer", "DIRECTOR TRIN")
        s_pos = st.text_input("Title", "CHIEF COMMANDER")
        s_img = st.file_uploader("Upload Digital Seal (PNG)", type=['png'])
        
        if st.button("🚀 INITIATE ENCRYPTION & BUILD", use_container_width=True):
            with st.spinner("Encrypting Data..."):
                fid = f"STRAT-{random.randint(100,999)}-{datetime.now().strftime('%H%M%S')}"
                pwd = ''.join(random.choices(string.digits, k=6))
                m_data = run_calculation(sat_obj, t_sel)
                st.session_state.pdf_blob = create_secure_pdf(selected_sat, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
                st.session_state.m_id, st.session_state.m_pwd = fid, pwd
                st.rerun()
    else:
        st.success(f"ARCHIVE READY: {st.session_state.m_id}")
        st.warning(f"PASSWORD: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD ENCRYPTED PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("RETURN TO DASHBOARD"):
            st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.open_sys: archive_dialog()

# Main Dashboard
@st.fragment(run_every=1.0)
def render_dashboard():
    # 1. Real-time Clock
    st.markdown(f'''<div class="clock-container"><span class="clock-text">{datetime.now(timezone.utc).strftime("%H:%M:%S")} UTC</span></div>''', unsafe_allow_html=True)
    
    m = run_calculation(sat_obj)
    
    # 2. Key Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT_VAL']:,.2f} KM", f"{random.uniform(-0.1, 0.1):.2f}")
    c2.metric("VELOCITY", f"{m['VEL_VAL']:,.0f} KM/H")
    c3.metric("CURRENT COORD", m["COORD"])
    
    # 3. Geospatial Visualization
    st.subheader("🌍 GEOSPATIAL COMMAND")
    m_cols = st.columns([2, 1])
    
    def draw_map(lt, ln, zm, k, tl, tn, height=450):
        fig = go.Figure()
        fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='#00ff00')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=18, color='red', symbol='rocket')))
        fig.update_layout(
            mapbox=dict(style="white-bg", 
                        layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}],
                        center=dict(lat=lt, lon=ln), zoom=zm),
            margin=dict(l=0,r=0,t=0,b=0), height=height, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]:
        draw_map(m['LAT'], m['LON'], z1, "TACTICAL_MAP", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]:
        draw_map(m['LAT'], m['LON'], z2, "GLOBAL_MAP", m["TAIL_LAT"], m["TAIL_LON"], height=450)

    # 4. Analytics & Telemetry
    st.divider()
    g_cols = st.columns(2)
    with g_cols[0]:
        fig_alt = go.Figure(go.Scatter(y=m["TAIL_ALT"], mode='lines+markers', line=dict(color='#00ff00'), fill='tozeroy'))
        fig_alt.update_layout(title="ALTITUDE HISTORY (KM)", template="plotly_dark", height=300, margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(fig_alt, use_container_width=True)
    
    with g_cols[1]:
        st.write("📋 **CORE TELEMETRY STREAM**")
        df_tele = pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 12, 4)])
        st.dataframe(df_tele, hide_index=True, use_container_width=True)

if sat_catalog:
    render_dashboard()
else:
    st.warning("⚠️ Waiting for Celestrak TLE Data... Please check your internet connection.")