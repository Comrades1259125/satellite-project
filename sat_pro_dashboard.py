import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import string
import qrcode
import base64
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84

# ==========================================
# 1. CORE SYSTEM & STATE
# ==========================================
st.set_page_config(page_title="V5950 ANALYTICS", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_ready' not in st.session_state: st.session_state.pdf_ready = False
if 'm_id' not in st.session_state: st.session_state.m_id = ""
if 'm_pwd' not in st.session_state: st.session_state.m_pwd = ""
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'qr_base64' not in st.session_state: st.session_state.qr_base64 = ""
if 'st_coords' not in st.session_state: st.session_state.st_coords = [17.16, 104.14]

@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    return {sat.name: sat for sat in load.tle_file(url)}

sat_catalog = init_system()
ts = load.timescale()

def get_real_mission_data(sat_obj):
    t_now = ts.now(); g = sat_obj.at(t_now); sub = wgs84.subpoint(g)
    v = np.linalg.norm(g.velocity.km_per_s)
    
    # ดึงข้อมูลจริงย้อนหลัง 100 นาที สำหรับกราฟ 3 ชุด
    hist_lat, hist_lon, hist_alt = [], [], []
    for i in range(0, 101, 5):
        t_hist = ts.from_datetime(datetime.now(timezone.utc) - timedelta(minutes=i))
        g_h = sat_obj.at(t_hist); sub_h = wgs84.subpoint(g_h)
        hist_lat.append(sub_h.latitude.degrees)
        hist_lon.append(sub_h.longitude.degrees)
        hist_alt.append(sub_h.elevation.km)

    tele = {"LATITUDE": f"{sub.latitude.degrees:.5f}°", "LONGITUDE": f"{sub.longitude.degrees:.5f}°",
            "ALTITUDE": f"{sub.elevation.km:.2f} KM", "VELOCITY": f"{v * 3600:.1f} KM/H"}
    for i in range(1, 37): tele[f"DATA_CH_{i:02d}"] = f"{random.uniform(10,99):.2f}"
    
    return {"LAT": sub.latitude.degrees, "LON": sub.longitude.degrees, "TELE": tele, 
            "G_LAT": hist_lat, "G_LON": hist_lon, "G_ALT": hist_alt}

# ==========================================
# 2. PDF & QR ENGINE
# ==========================================
class MISSION_PDF(FPDF):
    def draw_detailed_graph(self, x, y, w, h, data, title, color=(255,0,0)):
        self.set_draw_color(0, 0, 0); self.set_fill_color(255, 255, 255); self.rect(x, y, w, h, 'FD')
        self.set_font("Arial", 'B', 8); self.set_xy(x, y-5); self.cell(w, 5, title)
        self.set_font("Arial", '', 5); min_v, max_v = min(data), max(data)
        v_range = max_v - min_v if max_v != min_v else 1
        for i in range(6): # Gridlines
            grid_y = y + h - (i * (h / 5)); val_y = min_v + (i * (v_range / 5))
            self.set_draw_color(220, 220, 220); self.line(x, grid_y, x + w, grid_y)
            self.set_xy(x - 10, grid_y - 2); self.cell(8, 4, f"{val_y:.1f}", align='R')
        self.set_draw_color(*color); self.set_line_width(0.4)
        pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h)) for i,v in enumerate(data)]
        for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
        self.set_line_width(0.2)

def generate_qr_base64(text):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(text); qr.make()
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode(), buf

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m, qr_img_buf):
    pdf = MISSION_PDF()
    pdf.add_page() # Page 1: Table
    pdf.set_font("Arial", 'B', 18); pdf.cell(0, 15, "OFFICIAL MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", '', 10); pdf.cell(0, 8, f"ID: {f_id} | LOCATION: {addr['prov']}", ln=True, align='C')
    pdf.image(qr_img_buf, 170, 10, 25, 25)
    pdf.ln(5)
    items = list(m['TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.5, 9, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    pdf.add_page() # Page 2: 3 Graphs
    pdf.draw_detailed_graph(25, 30, 160, 45, m['G_LAT'], "1. LATITUDE REAL-TIME TRACKING", (200, 0, 0))
    pdf.draw_detailed_graph(25, 95, 160, 45, m['G_LON'], "2. LONGITUDE REAL-TIME TRACKING", (0, 150, 0))
    pdf.draw_detailed_graph(25, 160, 160, 45, m['G_ALT'], "3. ALTITUDE STABILITY (KM)", (0, 0, 200))
    
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 235, 40, 20)
    pdf.line(140, 255, 195, 255); pdf.set_xy(140, 257)
    pdf.set_font("Arial", 'B', 10); pdf.cell(55, 5, s_name.upper(), align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# ==========================================
# 3. INTERFACE (SIDEBAR)
# ==========================================
with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ASSET", list(sat_catalog.keys()))
    st.divider()
    a1 = st.text_input("Sub-District", "That Choeng Chum")
    a2 = st.text_input("District", "Mueang Sakon Nakhon")
    a3 = st.text_input("Province", "Sakon Nakhon")
    a4 = st.text_input("Zip Code", "47000")
    a5 = st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "zip": a4, "cntr": a5}
    if st.button("✅ LOCK STATION"): st.session_state.st_coords = [17.16, 104.14] if "Sakon" in a3 else [13.75, 100.5]
    st.divider()
    z1, z2, z3 = st.slider("Tactical", 1, 18, 12), st.slider("Global", 1, 10, 2), st.slider("Station", 1, 18, 15)
    if st.button("🧧 GENERATE REPORT", type="primary", use_container_width=True):
        st.session_state.pdf_ready = False; st.session_state.open_sys = True

# ==========================================
# 4. DIALOG (QR + REF ID MATCH)
# ==========================================
if st.session_state.open_sys:
    @st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
    def archive_dialog():
        if not st.session_state.pdf_ready:
            s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
            s_pos = st.text_input("Position", "CHIEF COMMANDER")
            s_img = st.file_uploader("Upload Signature (PNG)", type=['png'])
            if st.button("🚀 INITIATE SYSTEM", use_container_width=True):
                st.session_state.m_id = f"REF-{random.randint(100, 999)}-{datetime.now().strftime('%m%d')}"
                st.session_state.m_pwd = ''.join(random.choices(string.digits, k=6))
                m_data = get_real_mission_data(sat_catalog[sel_sat])
                st.session_state.qr_base64, qr_buf = generate_qr_base64(f"VERIFIED ID: {st.session_state.m_id}")
                st.session_state.pdf_blob = build_pdf(sel_sat, addr_data, s_name, s_pos, s_img, st.session_state.m_id, st.session_state.m_pwd, m_data, qr_buf)
                st.session_state.pdf_ready = True; st.rerun()
        else:
            st.markdown(f'''
                <div style="background:white; border:2px solid #333; padding:20px; text-align:center; color:black; border-radius:15px;">
                    <div style="font-size:11px; font-weight:bold; color:#666;">DOCUMENT ARCHIVE ID</div>
                    <div style="font-size:28px; font-weight:900; color:#d9534f; margin-bottom:15px;">{st.session_state.m_id}</div>
                    <div style="display:flex; justify-content:center; margin-bottom:15px;">
                        <div style="border:4px solid black; padding:5px; border-radius:10px;">
                            <img src="data:image/png;base64,{st.session_state.qr_base64}" width="150">
                        </div>
                    </div>
                    <hr style="border:0; border-top:1px solid #eee;">
                    <div style="font-size:11px; font-weight:bold; color:#666;">ENCRYPTION KEY</div>
                    <div style="font-size:48px; font-weight:900; letter-spacing:8px; color:black;">{st.session_state.m_pwd}</div>
                </div>
            ''', unsafe_allow_html=True)
            st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
            if st.button("RETURN"): st.session_state.open_sys = False; st.session_state.pdf_ready = False; st.rerun()
    archive_dialog()

# ==========================================
# 5. LIVE DASHBOARD
# ==========================================
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;"><div style="background:white; border:4px solid black; padding:10px 100px; border-radius:100px; text-align:center;"><div style="color:black; font-size:65px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</div></div></div>''', unsafe_allow_html=True)
    m = get_real_mission_data(sat_catalog[sel_sat])
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTITUDE", m['TELE']['ALTITUDE']); c2.metric("VELOCITY", m['TELE']['VELOCITY']); c3.metric("POSITION", m['TELE']['LATITUDE'])
    m_cols = st.columns(3)
    def draw_map(lt, ln, zm, k, color='red'):
        fig = go.Figure(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=18, color=color)))
        fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380)
        st.plotly_chart(fig, use_container_width=True, key=k)
    with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "t1")
    with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "t2")
    with m_cols[2]: draw_map(st.session_state.st_coords[0], st.session_state.st_coords[1], z3, "t3", "blue")
    st.table(pd.DataFrame([list(m["TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()