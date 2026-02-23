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
from PIL import Image, ImageDraw

# ==========================================
# 1. CORE DATA ENGINE (Full Features)
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try:
        return {sat.name: sat for sat in load.tle_file(url)}
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
    
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:.2f} KM/H",
        "SYS_LOCK": "AES-256",
        "OBC_STATUS": "NOMINAL",
        "GEN_TIME": t_input.strftime("%H:%M:%S")
    }
    for i in range(33): 
        tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    lats, lons, alts, vels = [], [], [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt)
        ps = wgs84.subpoint(g)
        lats.append(ps.latitude.degrees)
        lons.append(ps.longitude.degrees)
        alts.append(ps.elevation.km)
        vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
            "TAIL_LAT": lats, "TAIL_LON": lons, "TAIL_ALT": alts, "TAIL_VEL": vels, "RAW_TELE": tele}

# ==========================================
# 2. HD PDF ENGINE (Full Restore)
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
        self.set_draw_color(220, 220, 220); self.set_line_width(0.1)
        for i in range(1, 11): self.line(x + (i*w/10), y, x + (i*w/10), y+h)
        for i in range(1, 6): self.line(x, y + (i*h/5), x+w, y + (i*h/5))
        self.set_draw_color(0, 0, 0); self.set_line_width(0.3); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 9); self.set_xy(x, y-4); self.cell(w, 4, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.5)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    # PAGE 1: DATA TABLE
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 22); pdf.cell(0, 15, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.set_font("helvetica", 'B', 12); pdf.cell(0, 10, f"ARCHIVE ID: {f_id}", ln=True, align='C')
    pdf.set_font("helvetica", '', 9); pdf.cell(0, 6, f"ASSET: {sat_name} | STATION: {addr['sub']}, {addr['dist']}, {addr['prov']}".upper(), ln=True, align='C')
    pdf.ln(5)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("helvetica", 'B', 7); pdf.cell(15, 8, f" {items[i+j][0]}:", border='LTB')
                pdf.set_font("helvetica", '', 7); pdf.cell(32.25, 8, f"{items[i+j][1]}", border='RTB')
        pdf.ln()
    
    # PAGE 2: GRAPHS & SIGNATURE
    pdf.add_page()
    pdf.draw_precision_graph(20, 30, 170, 60, "ORBITAL LATITUDE TRACKING", m['TAIL_LAT'], (0, 80, 180))
    pdf.draw_precision_graph(20, 110, 80, 45, "VELOCITY (KM/H)", m['TAIL_VEL'], (160, 100, 0))
    pdf.draw_precision_graph(110, 110, 80, 45, "ALTITUDE (KM)", m['TAIL_ALT'], (0, 120, 60))
    
    qr_buf = generate_verified_qr(f_id)
    pdf.image(qr_buf, 20, 185, 45, 60)
    
    pdf.line(110, 235, 190, 235)
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 140, 205, 30, 25)
    pdf.set_xy(110, 237); pdf.set_font("helvetica", 'B', 11); pdf.cell(80, 6, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("helvetica", 'I', 9); pdf.cell(80, 5, s_pos.upper(), align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. INTERFACE (Locked & Secure)
# ==========================================
st.set_page_config(page_title="V5950 MISSION DASHBOARD", layout="wide")

if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sat_name = st.selectbox("ASSET", list(sat_catalog.keys()) if sat_catalog else ["LOADING..."])
    
    st.subheader("📍 STATION ADDRESS")
    a1, a2 = st.text_input("Sub-District", "Phra Borom"), st.text_input("District", "Phra Nakhon")
    a3, a4 = st.text_input("Province", "Bangkok"), st.text_input("Country", "Thailand")
    addr_data = {"sub": a1, "dist": a2, "prov": a3, "cntr": a4}
    
    st.divider()
    z1 = st.slider("Tactical Zoom", 1, 18, 12)
    z2 = st.slider("Global Zoom", 1, 10, 2)
    z3 = st.slider("Station Zoom", 1, 18, 15)
    
    if st.button("🧧 EXECUTE REPORT", use_container_width=True, type="primary"):
        st.session_state.pdf_blob = None
        st.session_state.open_sys = True

# --- MODAL DIALOG (Isolated) ---
@st.dialog("📋 OFFICIAL ARCHIVE ACCESS")
def archive_dialog():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Time Mode", ["Live", "Predictive"], horizontal=True)
        t_sel = None
        if mode == "Predictive":
            c1, c2 = st.columns(2)
            t_sel = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
        
        s_name = st.text_input("Signer Name", "DIRECTOR TRIN")
        s_pos = st.text_input("Position", "CHIEF COMMANDER")
        s_img = st.file_uploader("Digital Seal (PNG)", type=['png'])
        
        if st.button("🚀 GENERATE ARCHIVE", use_container_width=True):
            fid = f"REF-{random.randint(100, 999)}-{datetime.now().strftime('%m%d')}"
            pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_name], t_sel)
            st.session_state.pdf_blob = build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
            st.session_state.m_id, st.session_state.m_pwd = fid, pwd
            st.rerun()
    else:
        st.success("ENCRYPTION COMPLETE")
        st.markdown(f'''<div style="background:white; border:3px solid black; padding:15px; text-align:center; color:black;">
            <div style="font-size:14px;">ID: {st.session_state.m_id}</div>
            <div style="font-size:26px; font-weight:900;">PASS: {st.session_state.m_pwd}</div>
        </div>''', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD ENCRYPTED PDF", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
        if st.button("RETURN TO DASHBOARD"):
            st.session_state.open_sys = False
            st.session_state.pdf_blob = None
            st.rerun()

if st.session_state.open_sys: archive_dialog()

# --- MAIN DASHBOARD (Fragmented) ---
@st.fragment(run_every=1.0)
def dashboard():
    st.markdown(f'''<div style="display:flex; justify-content:center; margin-bottom:20px;">
        <div style="background:white; border:5px solid black; padding:10px 50px; border-radius:100px; text-align:center;">
            <span style="color:black; font-size:55px; font-weight:900; font-family:monospace;">{datetime.now(timezone.utc).strftime("%H:%M:%S")}</span>
        </div></div>''', unsafe_allow_html=True)
    
    if sat_catalog and sat_name != "LOADING...":
        m = run_calculation(sat_catalog[sat_name])
        c1, c2, c3 = st.columns(3)
        c1.metric("ALTITUDE", f"{m['ALT_VAL']:.2f} KM")
        c2.metric("VELOCITY", f"{m['VEL_VAL']:.2f} KM/H")
        c3.metric("COORD", f"{m['LAT']:.3f}, {m['LON']:.3f}")

        st.subheader("🌍 GEOSPATIAL COMMAND")
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

        st.subheader("📊 PERFORMANCE ANALYTICS")
        g_cols = st.columns(2)
        fig_opt = dict(template="plotly_dark", height=250, margin=dict(l=10, r=10, t=30, b=10))
        with g_cols[0]: st.plotly_chart(go.Figure(go.Scatter(y=m["TAIL_ALT"], mode='lines', line=dict(color='#00ff00'))).update_layout(title="ALTITUDE TRACK", **fig_opt), use_container_width=True)
        with g_cols[1]: st.plotly_chart(go.Figure(go.Scatter(y=m["TAIL_VEL"], mode='lines', line=dict(color='#ffff00'))).update_layout(title="VELOCITY TRACK", **fig_opt), use_container_width=True)

        st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()