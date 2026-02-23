import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timedelta, timezone
from fpdf import FPDF # ตอนนี้ใช้ fpdf2 แทนใน requirements
from pypdf import PdfReader, PdfWriter
import qrcode
from io import BytesIO
from skyfield.api import load, wgs84
from geopy.geocoders import Nominatim
from PIL import Image

# ==========================================
# 1. CORE ENGINE & GEOPY
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

def get_station_coords(sub, dist, prov, country):
    full_address = f"{sub}, {dist}, {prov}, {country}"
    try:
        geolocator = Nominatim(user_agent="v5950_final_system")
        location = geolocator.geocode(full_address)
        if location: return location.latitude, location.longitude
    except: pass
    return 13.7563, 100.5018

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km); vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "OBC_STATUS": "ACTIVE",
        "COM_MODE": "ENCRYPTED",
        "SYS_SYNC": "LOCKED",
        "MISSION_PH": "PHASE-04",
        "GEN_TIME": t_input.strftime("%H:%M:%S")
    }
    
    return {
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels,
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "RAW_TELE": tele
    }

# ==========================================
# 2. HD PDF ENGINE (COMPATIBLE WITH FPDF2)
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180)):
        self.set_fill_color(252, 252, 252); self.rect(x, y, w, h, style='F')
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
    pdf.set_font("helvetica", 'B', 24); pdf.cell(0, 12, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 14); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.ln(5)
    
    # Graphs
    pdf.draw_precision_graph(25, 60, 160, 65, "ORBITAL TRACKING", m['TAIL_LAT'])
    
    # แก้ไข QR Code และ Signature โดยใช้ PIL Image ตรงเข้า fpdf2
    qr_img = qrcode.make(f_id).convert('RGB')
    pdf.image(qr_img, x=20, y=190, w=45) 
    
    pdf.line(105, 230, 195, 230)
    if s_img:
        seal = Image.open(s_img).convert('RGBA')
        pdf.image(seal, x=135, y=205, w=30)
    
    pdf.set_xy(105, 232); pdf.set_font("helvetica", 'B', 11); pdf.cell(90, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(105); pdf.set_font("helvetica", 'I', 9); pdf.cell(90, 5, s_pos.upper(), align='C')
    
    # Encryption using PyPDF
    raw_pdf_bytes = pdf.output()
    reader = PdfReader(BytesIO(raw_pdf_bytes)); writer = PdfWriter()
    writer.add_page(reader.pages[0]); writer.encrypt(pwd)
    final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE & DIALOG
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

if 'st_lat' not in st.session_state: st.session_state.st_lat, st.session_state.st_lon = 13.7563, 100.5018
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()))
    
    st.subheader("📍 STATION LOOKUP")
    a1 = st.text_input("Sub-District", "Phra Borom")
    a2 = st.text_input("District", "Phra Nakhon")
    a3 = st.text_input("Province", "Bangkok")
    a4 = st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    
    if st.button("🔍 FETCH & LOCK STATION", use_container_width=True):
        lat, lon = get_station_coords(a1, a2, a3, a4)
        st.session_state.st_lat, st.session_state.st_lon = lat, lon
        st.toast("STATION UPDATED")

    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.pdf_blob = None
        st.session_state.open_sys = True

@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        # กู้คืน Predictive Mode
        mode = st.radio("Time Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            d = c1.date_input("Select Date")
            t = c2.time_input("Select Time")
            t_sel = datetime.combine(d, t).replace(tzinfo=timezone.utc)
            
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        
        if st.button("🚀 INITIATE ARCHIVE", use_container_width=True):
            fid = f"REF-{random.randint(100, 999)}-{datetime.now().strftime('%y%m%d')}"
            pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name], t_sel)
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd; st.rerun()
    else:
        st.markdown(f"""<div style="background:white; border:5px solid black; padding:20px; text-align:center; color:black; border-radius:10px;">
            <p style="margin:0;">ARCHIVE ID: <b>{st.session_state.m_id}</b></p>
            <h1 style="margin:0; font-size:45px; letter-spacing:3px;">{st.session_state.m_pwd}</h1></div>""", unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD ENCRYPTED PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("RETURN"): st.session_state.open_sys = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.open_sys: archive_dialog()

# ==========================================
# 4. DASHBOARD (3 MAPS + TAIL)
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="text-align:center; margin-bottom:20px;"><span style="color:black; font-size:40px; font-weight:900; background:white; border:4px solid black; padding:5px 40px; border-radius:50px; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span></div>''', unsafe_allow_html=True)
    m = run_calculation(sat_catalog[sat_name])
    
    m_cols = st.columns([1, 1, 1])
    def draw_map(lt, ln, zm, k, tl=None, tn=None, color='red'):
        fig = go.Figure()
        if tl and tn: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
        fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=k)

    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
    with m_cols[2]: draw_map(st.session_state.st_lat, st.session_state.st_lon, z3, "S1", color='cyan')

    # Telemetry Table
    st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+3] for i in range(0, 9, 3)]))

dashboard()