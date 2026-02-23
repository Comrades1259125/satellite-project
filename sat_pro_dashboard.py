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
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

# ระบบจำลองการหาพิกัดจากชื่อที่อยู่ (Geocoding)
def get_station_coords(addr_dict):
    # ค่าเริ่มต้น (กรุงเทพฯ)
    base_lat, base_lon = 13.7505, 100.4930
    
    # ถ้ามีการเปลี่ยนชื่อจังหวัด/เขต ระบบจะจำลองการขยับพิกัด
    # (ในระบบจริงส่วนนี้จะเชื่อมต่อกับ Google Maps API)
    seed_str = f"{addr_dict['sub']}{addr_dict['dist']}{addr_dict['prov']}"
    random.seed(seed_str)
    
    # ถ้าเป็นค่า Default ให้ล็อกที่เดิมเป๊ะๆ
    if addr_dict['sub'] == "Phra Borom" and addr_dict['prov'] == "Bangkok":
        return base_lat, base_lon
    
    # ถ้าเปลี่ยนที่อยู่ ให้จำลองพิกัดใหม่ใกล้เคียง
    lat = base_lat + random.uniform(-0.5, 0.5)
    lon = base_lon + random.uniform(-0.5, 0.5)
    return lat, lon

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "EPS_BATT_V": f"{random.uniform(28.0, 32.0):.2f} V",
        "EPS_SOLAR_A": f"{random.uniform(5.5, 8.2):.2f} A",
        "TCS_HEATER": "NOMINAL",
        "OBC_STATUS": "ACTIVE",
        "COM_MODE": "ENCRYPTED",
        "SYS_SYNC": "LOCKED",
        "ANT_POS": "DEPLOYED",
        "MISSION_PH": "PHASE-04",
        "GEN_TIME": "REAL-TIME"
    }

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
# 2. HD PDF ENGINE
# ==========================================
def generate_verified_qr(data_text):
    qr = qrcode.QRCode(border=2)
    qr.add_data(data_text); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    w, h = img.size
    canvas = Image.new('RGB', (w + 40, h + 90), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([5, 5, w + 35, h + 85], outline="darkgreen", width=5)
    canvas.paste(img, (20, 15))
    draw.text((w/2 + 20, h + 55), "VERIFIED ARCHIVE", fill="black", anchor="mm")
    buf = BytesIO(); canvas.save(buf, format="PNG"); return buf

class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, 'F')
        self.set_draw_color(230, 230, 230); self.set_line_width(0.05)
        for i in range(1, 41): self.line(x + (i*w/40), y, x + (i*w/40), y+h)
        for i in range(1, 21): self.line(x, y + (i*h/20), x+w, y + (i*h/20))
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
    pdf.ln(10)
    pdf.set_font("helvetica", 'B', 24); pdf.cell(0, 12, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 14); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    loc = f"ASSET: {sat_name.upper()} | STATION: {addr['sub']}, {addr['dist']}, {addr['prov']}, {addr['cntr']}".upper()
    pdf.set_font("helvetica", '', 10); pdf.cell(0, 8, loc, ln=True, align='C')
    pdf_data = pdf.output(dest='S').encode('latin-1')
    raw = BytesIO(pdf_data); reader = PdfReader(raw); writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. RESPONSIVE INTERFACE
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

st.markdown("""
    <style>
    @media (max-width: 600px) { .clock-text { font-size: 35px !important; } }
    .stButton>button { height: 3em; width: 100%; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

clock_spot = st.empty()

def reset_sys():
    st.session_state.open_sys = False
    st.session_state.pdf_blob = None

# Sidebar Setup
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()), on_change=reset_sys)
    st.subheader("📍 STATION LOCATION")
    a1 = st.text_input("Sub-District", "Phra Borom", on_change=reset_sys)
    a2 = st.text_input("District", "Phra Nakhon", on_change=reset_sys)
    a3 = st.text_input("Province", "Bangkok", on_change=reset_sys)
    a4 = st.text_input("Country", "Thailand", on_change=reset_sys)
    
    # คำนวณพิกัดสถานีจากที่อยู่
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    st_lat, st_lon = get_station_coords(addr_data)
    
    if st.button("📍 CONFIRM LOCATION", use_container_width=True):
        st.toast(f"STATION LOCKED: {st_lat:.4f}, {st_lon:.4f}")
        reset_sys()

    z1 = st.slider("Tactical", 1, 18, 12, on_change=reset_sys)
    z2 = st.slider("Global", 1, 10, 2, on_change=reset_sys)
    z3 = st.slider("Station", 1, 18, 15, on_change=reset_sys)
    
    st.markdown("---")
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"): st.session_state.open_sys = True

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        if st.button("🚀 INITIATE", use_container_width=True):
            fid = f"REF-{random.randint(100, 999)}"
            pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name])
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.write(f"ID: {st.session_state.m_id} | PASS: {st.session_state.m_pwd}")
        st.download_button("📥 DOWNLOAD", st.session_state.pdf_blob, "report.pdf")
        if st.button("CLOSE"): st.session_state.open_sys = False; st.rerun()

if st.session_state.open_sys: archive_dialog()

@st.fragment(run_every=1.0)
def dashboard():
    clock_spot.markdown(f'''<div style="text-align:center;"><span style="color:black; font-size:40px; font-weight:900; background:white; border:4px solid black; padding:5px 40px; border-radius:50px;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div>''', unsafe_allow_html=True)
    m = run_calculation(sat_catalog[sat_name])
    
    st.subheader("🌍 GEOSPATIAL COMMAND")
    m_cols = st.columns([1, 1, 1])
    
    def draw_map(lt, ln, zm, k, tl, tn, color='red'):
        fig = go.Figure()
        if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color=color)))
        fig.update_layout(
            mapbox=dict(
                style="white-bg", 
                layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], 
                center=dict(lat=lt, lon=ln), zoom=zm
            ), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True, key=k, config={'displayModeBar': False})
        
    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    
    # --- แผนที่ที่ 3: ล็อกตามพิกัดสถานีภาคพื้นดิน (Station) ---
    with m_cols[2]: draw_map(st_lat, st_lon, z3, "S1", [], [], color='cyan')

    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 12, 4)]))

dashboard()