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
# 1. CORE DATA ENGINE (TLE & PHYSICS)
# ==========================================
@st.cache_resource
def init_system():
    # ดึงข้อมูลดาวเทียมจริงจาก Celestrak
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try:
        data = load.tle_file(url)
        return {sat.name: sat for sat in data}
    except:
        return {}

sat_catalog = init_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # จำลอง Telemetry 40 พารามิเตอร์
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.0, 32.0):.2f} V",
        "EPS_TEMP": f"{random.uniform(22, 28):.2f} C",
        "OBC_STATUS": "ACTIVE",
        "SYS_LOCK": "AES-RSA",
        "MISSION_PH": "PHASE-04"
    }
    # เติมให้ครบ 40 ตัวสำหรับตาราง
    for i in range(31):
        tele[f"PARAM_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # ข้อมูลประวัติวิถีโคจร
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}", 
            "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, "RAW_TELE": tele}

# ==========================================
# 2. HD PDF & QR ENGINE
# ==========================================
def generate_verified_qr(data_text):
    qr = qrcode.QRCode(border=2)
    qr.add_data(data_text); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    buf = BytesIO(); img.save(buf, format="PNG"); return buf

class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.4); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title.upper())
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 22); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 12); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.ln(5)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.set_font("helvetica", '', 7.5); pdf.cell(47.25, 8, f" {items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()
    pdf.add_page()
    pdf.draw_precision_graph(25, 30, 160, 65, "ORBITAL LATITUDE TRACKING", m['TAIL_LAT'])
    pdf.draw_precision_graph(25, 115, 75, 50, "VELOCITY (KM/H)", m['TAIL_VEL'], (160, 100, 0))
    pdf.draw_precision_graph(110, 115, 75, 50, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 60))
    qr_buf = generate_verified_qr(f_id)
    pdf.image(qr_buf, 20, 190, 45, 45)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 135, 200, 30, 22)
    pdf.set_xy(105, 225); pdf.set_font("helvetica", 'B', 11); pdf.cell(90, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(105); pdf.set_font("helvetica", 'I', 9); pdf.cell(90, 5, s_pos.upper(), align='C')
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. INTERFACE CONTROL
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()) if sat_catalog else ["Loading..."])
    st.subheader("📍 STATION INFO")
    a1 = st.text_input("District", "Phra Nakhon")
    a2 = st.text_input("Province", "Bangkok")
    addr_data = {"sub": a1, "prov": a2}
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"): st.session_state.open_sys = True

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        if st.button("🚀 INITIATE", use_container_width=True):
            fid = f"REF-{random.randint(100, 999)}"
            pwd = ''.join(random.choices(string.digits, k=6))
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, run_calculation(sat_catalog[sat_name]))
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.success(f"ID: {st.session_state.m_id} | PASS: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"REPORT_{st.session_state.m_id}.pdf")
        if st.button("CLOSE"): st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.open_sys: archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    m = run_calculation(sat_catalog[sat_name])
    st.markdown(f'''<div style="display:flex; justify-content:center;"><div style="background:white; border:5px solid black; padding:5px 40px; border-radius:100px; text-align:center;"><span style="color:black; font-size:45px; font-weight:900;">{datetime.now(timezone.utc).strftime("%H:%M:%S")} UTC</span></div></div>''', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", f"{m['ALT_VAL']:.2f} KM"); c2.metric("VELOCITY", f"{m['VEL_VAL']:.2f} KM/H"); c3.metric("COORD", m["COORD"])
    st.subheader("🌍 GEOSPATIAL COMMAND")
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, tl, tn):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)
    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], [])
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

if sat_catalog: dashboard()