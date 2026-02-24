import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import qrcode
from datetime import datetime, timedelta, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84

# --- พารามิเตอร์ 40 รายการ ---
TELE_LABELS = [
    "BAT_VOLT", "BAT_TEMP", "SOL_PWR_A", "SOL_PWR_B", "BUS_CURR",
    "RW_X_RPM", "RW_Y_RPM", "RW_Z_RPM", "GYRO_STAB", "MAG_INTEN",
    "CPU_LOAD", "MEM_FREE", "OS_STATUS", "UL_SIGNAL", "DL_BANDW",
    "THERM_SHLD", "CORE_TEMP", "ANT_ALIGN", "S_BAND_ACT", "X_BAND_HZ",
    "OBC_HEALTH", "EPS_CONV", "TTC_DELAY", "ADCS_ERR", "AOCS_SYNC",
    "PROP_TANK", "FUEL_LVL", "THRUST_A", "THRUST_B", "PLD_ACTIVE",
    "IMG_STACK", "LENS_TEMP", "CCD_SENS", "RAD_TOTAL", "STAR_TRK1",
    "STAR_TRK2", "HOR_SENS", "GPS_PREC", "CLK_OFFSET", "MISSION_ST"
]

@st.cache_resource
def init_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

LOC_DB = {
    "Sakon Nakhon": {"lat": 17.1612, "lon": 104.1486, "tz": 7},
    "Bangkok": {"lat": 13.7563, "lon": 100.5018, "tz": 7},
    "London": {"lat": 51.5074, "lon": -0.1278, "tz": 0},
    "New York": {"lat": 40.7128, "lon": -74.0060, "tz": -5}
}

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t); subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    data = {"LAT": f"{subpoint.latitude.degrees:.4f}", "LON": f"{subpoint.longitude.degrees:.4f}",
            "ALT": f"{subpoint.elevation.km:.2f}", "VEL": f"{v_km_s * 3600:.2f}"}
    for label in TELE_LABELS:
        if label not in data: data[label] = f"{random.uniform(10, 99):.2f}"
    history = {"lats": [], "lons": [], "vels": [], "alts": []}
    for i in range(0, 101, 5):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); s = wgs84.subpoint(g)
        history["lats"].append(s.latitude.degrees); history["lons"].append(s.longitude.degrees)
        history["vels"].append(np.linalg.norm(g.velocity.km_per_s) * 3600)
        history["alts"].append(s.elevation.km)
    return data, history

class ULTIMATE_PDF(FPDF):
    def draw_graph(self, x, y, w, h, title, data, color):
        self.set_fill_color(245); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0); self.rect(x, y, w, h)
        self.set_font("Arial", 'B', 10); self.set_xy(x, y-5); self.cell(w, 5, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.6)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m_main, m_hist):
    pdf = ULTIMATE_PDF()
    # --- หน้าที่ 1: ข้อมูลที่อยู่และ Telemetry ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "MISSION STRATEGIC DATA - PAGE 1", ln=True, align='C')
    pdf.set_font("Arial", 'B', 8); addr_txt = f"ZONE: {addr['z']} | COUNTRY: {addr['c']} | PROV: {addr['p']} | DIST: {addr['d']} | SUB: {addr['s']}"
    pdf.cell(0, 7, addr_txt.upper(), border=1, ln=True, align='C')
    pdf.ln(5); pdf.set_font("Courier", 'B', 8)
    items = list(m_main.items())
    for i in range(0, 44, 4):
        for j in range(4):
            if i+j < len(items): pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    # --- หน้าที่ 2: กราฟ, QR Code และลายเซ็น ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "ANALYTICS & VERIFICATION - PAGE 2", ln=True, align='C')
    pdf.ln(10)
    pdf.draw_graph(10, 30, 190, 50, "LATITUDE TRAJECTORY ANALYSIS", m_hist["lats"], (0, 102, 204))
    pdf.draw_graph(10, 100, 190, 50, "ORBITAL VELOCITY (KM/H)", m_hist["vels"], (204, 0, 0))
    pdf.draw_graph(10, 170, 190, 50, "ALTITUDE VARIATION (KM)", m_hist["alts"], (0, 153, 51))
    
    # QR Code สั่งย้ายมาไว้หน้า 2 ท้ายกระดาษ
    pdf.set_draw_color(0); pdf.rect(15, 235, 40, 45)
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 17.5, 237, 35, 35)
    pdf.set_xy(15, 272); pdf.set_font("Arial", 'B', 7); pdf.cell(40, 5, "SECURE VERIFICATION", align='C', ln=True)
    
    # ลายเซ็นย้ายมาหน้า 2
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 235, 30, 20)
    pdf.line(120, 265, 190, 265); pdf.set_xy(120, 267); pdf.set_font("Arial", 'B', 10); 
    pdf.cell(70, 5, s_name.upper() if s_name else "DIRECTOR", align='C', ln=True)
    pdf.set_x(120); pdf.set_font("Arial", 'I', 8); pdf.cell(70, 5, s_pos.upper() if s_pos else "COMMANDER", align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

# --- UI เหมือนเดิมห้ามเปลี่ยน ---
st.set_page_config(page_title="ZENITH V8.6", layout="wide")
if 'show_modal' not in st.session_state: st.session_state.show_modal = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ MISSION CONTROL")
    sel_sat = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
    z_a, c_a, p_a = st.text_input("โซน", "Asia"), st.text_input("ประเทศ", "Thailand"), st.selectbox("จังหวัด (Sync Time)", list(LOC_DB.keys()))
    d_a, s_a = st.text_input("อำเภอ", "Mueang"), st.text_input("ตำบล", "That Choeng Chum")
    if st.button("✅ CONFIRM LOCATION & SYNC", use_container_width=True): st.toast(f"Synced to {p_a}")
    loc_info = LOC_DB.get(p_a); st_lat, st_lon, st_tz = loc_info["lat"], loc_info["lon"], loc_info["tz"]
    st.divider()
    z1 = st.slider("Tactical", 1, 18, 12, key="z1"); z2 = st.slider("Global", 1, 10, 2, key="z2"); z3 = st.slider("Station", 1, 18, 15, key="z3")
    if st.button("🧧 GENERATE MISSION ARCHIVE", use_container_width=True, type="primary"): st.session_state.show_modal = True

@st.dialog("📋 ARCHIVE ACCESS CONTROL")
def modal():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Analytics", ["Live Stream", "Predictive Orbit"], horizontal=True)
        t_target = None
        if mode == "Predictive Orbit":
            c1, c2 = st.columns(2); t_target = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
        s_name, s_pos = st.text_input("Officer Name"), st.text_input("Designation")
        s_img = st.file_uploader("Seal (PNG)", type=['png'])
        if st.button("🚀 EXECUTE ENCRYPTION"):
            fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%m%d')}"
            pwd = "".join([str(random.randint(0,9)) for _ in range(6)])
            m_main, m_hist = run_calculation(sat_catalog[sel_sat], t_target)
            addr = {"z": z_a, "c": c_a, "p": p_a, "d": d_a, "s": s_a}
            st.session_state.pdf_blob = build_pdf(sel_sat, addr, s_name, s_pos, s_img, fid, pwd, m_main, m_hist)
            st.session_state.fid, st.session_state.pwd = fid, pwd
            st.rerun()
    else:
        st.markdown(f'<div style="border:4px solid black; padding:25px; border-radius:15px; text-align:center; background:white; color:black;"><p style="color:gray;">ARCHIVE ID</p><h2 style="color:red; font-weight:900;">{st.session_state.fid}</h2><hr><p style="color:gray;">PASSKEY</p><h1 style="font-weight:900; letter-spacing:15px;">{st.session_state.pwd}</h1></div>', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD PDF", st.session_state.pdf_blob, f"{st.session_state.fid}.pdf", use_container_width=True)
        if st.button("RETURN"): st.session_state.show_modal = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.show_modal: modal()

@st.fragment(run_every=1.0)
def main_dashboard():
    synced_time = (datetime.now(timezone.utc) + timedelta(hours=st_tz)).strftime("%H:%M:%S")
    st.markdown(f'<div style="text-align:center; background:white; border:5px solid black; border-radius:100px; padding:15px; margin-bottom:20px;"><span style="color:black; font-size:70px; font-weight:900; font-family:monospace;">{synced_time}</span><p style="margin:0; font-weight:bold; color:gray;">LOCATION: {p_a}</p></div>', unsafe_allow_html=True)
    if sat_catalog and sel_sat in sat_catalog:
        m_main, m_hist = run_calculation(sat_catalog[sel_sat])
        cols = st.columns(3)
        cols[0].metric("ALTITUDE", f"{m_main['ALT']} KM"); cols[1].metric("VELOCITY", f"{m_main['VEL']} KM/H"); cols[2].metric("POSITION", f"{m_main['LAT']}, {m_main['LON']}")
        m_cols = st.columns(3)
        def draw_map(lt, ln, zm, k, tl, tn):
            fig = go.Figure()
            if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(color='yellow', width=2)))
            fig.add_trace(go.Scattermapbox(lat=[float(lt)], lon=[float(ln)], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=float(lt), lon=float(ln)), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)
        with m_cols[0]: draw_map(m_main['LAT'], m_main['LON'], z1, "m1", m_hist["lats"], m_hist["lons"])
        with m_cols[1]: draw_map(m_main['LAT'], m_main['LON'], z2, "m2", m_hist["lats"], m_hist["lons"])
        with m_cols[2]: draw_map(st_lat, st_lon, z3, "m3", [], [])
        st.subheader("📊 40-PARAMETER TELEMETRY STREAM")
        st.table(pd.DataFrame([list(m_main.items())[i:i+4] for i in range(0, 44, 4)]))

main_dashboard()