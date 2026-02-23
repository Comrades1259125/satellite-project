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
from skyfield.api import load, wgs84, Topos
from PIL import Image, ImageDraw

# ==========================================
# 1. CORE DATA & PREDICTION ENGINE
# ==========================================
@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, st_lat, st_lon, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # --- [NEW] PASS PREDICTION LOGIC ---
    station = wgs84.latlon(st_lat, st_lon)
    difference = sat_obj - station
    topocentric = difference.at(t)
    alt, az, distance = topocentric.altaz()
    
    # --- [NEW] DYNAMIC HEALTH AI ---
    # จำลองค่าให้สัมพันธ์กับฟิสิกส์ (เช่น ยิ่งใกล้โลก ยิ่งร้อน)
    temp_base = 20.0 + (500 / max(subpoint.elevation.km, 1)) 
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "SIG_ELEV": f"{alt.degrees:.2f}°",
        "SIG_AZIM": f"{az.degrees:.2f}°",
        "SIG_DIST": f"{distance.km:.2f} KM",
        "EPS_TEMP": f"{temp_base + random.uniform(-1, 1):.2f} C",
        "OBC_STATUS": "ACTIVE" if alt.degrees > 0 else "STANDBY",
        "MISSION_PH": "PHASE-04",
        "SYS_SYNC": "LOCKED",
        "GEN_TIME": t_input.strftime("%H:%M:%S")
    }

    # ข้อมูลย้อนหลังสำหรับกราฟ
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    # --- [NEW] FOOTPRINT CALCULATION ---
    # รัศมีครอบคลุม (พื้นฐานจากความสูง)
    horizon_dist = np.sqrt(2 * 6371 * subpoint.elevation.km)
    
    return {
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "FOOTPRINT": horizon_dist, "IN_VIEW": alt.degrees > 0,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, "RAW_TELE": tele
    }

# ==========================================
# 2. HD PDF ENGINE (PREMIUM)
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(220, 220, 220); self.set_line_width(0.1)
        for i in range(1, 11): self.line(x + (i*w/10), y, x + (i*w/10), y+h)
        self.set_draw_color(0, 0, 0); self.set_line_width(0.4); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title.upper())
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.7)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 24); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 12); pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.set_fill_color(30, 30, 40); pdf.set_text_color(255, 255, 255); pdf.set_font("helvetica", 'B', 9)
    loc = f"ASSET: {sat_name.upper()} | STATION: {addr['sub']}, {addr['dist']}, {addr['prov']}".upper()
    pdf.cell(0, 10, f"  {loc}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(5)

    items = list(m['RAW_TELE'].items())
    for i in range(0, len(items), 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", 'B', 7); pdf.set_fill_color(240, 240, 245)
                pdf.cell(47.5, 6, f" {items[i+j][0]}", border='LTR', fill=True)
        pdf.ln()
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", '', 8)
                pdf.cell(47.5, 7, f" {items[i+j][1]}", border='LBR')
        pdf.ln(2)

    pdf.add_page()
    pdf.draw_precision_graph(20, 30, 170, 70, "ORBITAL TRACKING", m['TAIL_LAT'])
    pdf.draw_precision_graph(20, 120, 80, 55, "VELOCITY (KM/H)", m['TAIL_VEL'], (180, 100, 0))
    pdf.draw_precision_graph(110, 120, 80, 55, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 80))
    
    qr_img = qrcode.make(f_id).convert('RGB')
    pdf.image(qr_img, x=20, y=200, w=40)
    pdf.line(110, 250, 190, 250)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), x=140, y=225, w=30)
    pdf.set_xy(110, 252); pdf.set_font("helvetica", 'B', 12); pdf.cell(80, 7, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("helvetica", 'I', 10); pdf.cell(80, 5, s_pos.upper(), align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (IPAD/MOBILE READY)
# ==========================================
st.set_page_config(page_title="V5950 ULTIMATE", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'st_lat' not in st.session_state: st.session_state.st_lat, st.session_state.st_lon = 13.75, 100.5

with st.sidebar:
    st.header("🛰️ STRATEGIC CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 STATION COORDINATES")
    lat_in = st.number_input("Lat", value=st.session_state.st_lat, format="%.4f")
    lon_in = st.number_input("Lon", value=st.session_state.st_lon, format="%.4f")
    st.session_state.st_lat, st.session_state.st_lon = lat_in, lon_in
    
    addr_data = {"sub": "BANGKOK", "dist": "PHRA NAKHON", "prov": "TH"}
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 14)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.open_sys = True

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            t_sel = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
        
        s_name = st.text_input("Signer", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        
        if st.button("🚀 GENERATE", use_container_width=True):
            m_data = run_calculation(sat_catalog[sat_name], st.session_state.st_lat, st.session_state.st_lon, t_sel)
            fid = f"REF-{random.randint(100, 999)}-{datetime.now().strftime('%Y%m%d')}"
            pwd = ''.join(random.choices(string.digits, k=6))
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.markdown(f'<div style="background:white; border:4px solid black; padding:20px; text-align:center; color:black;">ID: {st.session_state.m_id}<br><b style="font-size:30px;">{st.session_state.m_pwd}</b></div>', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("RETURN"): st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.open_sys: archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="text-align:center; margin-bottom:20px;"><div style="display:inline-block; background:white; border:5px solid black; padding:5px 50px; border-radius:100px;"><span style="color:black; font-size:45px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div></div>''', unsafe_allow_html=True)
    
    m = run_calculation(sat_catalog[sat_name], st.session_state.st_lat, st.session_state.st_lon)
    
    # Status Indicators
    c1, c2, c3 = st.columns(3)
    status_color = "green" if m['IN_VIEW'] else "gray"
    c1.markdown(f"**SIGNAL STATUS:** <span style='color:{status_color}'>{'● ONLINE' if m['IN_VIEW'] else '○ OUT OF RANGE'}</span>", unsafe_allow_html=True)
    c2.metric("ALTITUDE", f"{m['ALT_VAL']:.2f} KM")
    c3.metric("VELOCITY", f"{m['VEL_VAL']:.2f} KM/H")

    # Maps
    m_cols = st.columns([1, 1, 1])
    def draw_map(lt, ln, zm, k, tl, tn, foot=0):
        fig = go.Figure()
        # [NEW] FOOTPRINT CIRCLE
        if foot > 0:
            fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=zm*15, color='rgba(0, 255, 0, 0.1)')))
        fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=14, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"], m['FOOTPRINT'])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(st.session_state.st_lat, st.session_state.st_lon, z3, "S1", [], [], 0)

    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 12, 4)]))

dashboard()