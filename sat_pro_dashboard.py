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

# --- หมวดหมู่ข้อมูล 40 รายการที่ไม่ซ้ำกัน ---
TELEMETRY_LABELS = [
    "BAT_VOLT", "BAT_TEMP", "SOLAR_PANEL_A", "SOLAR_PANEL_B", "BUS_CURRENT",
    "REACTION_WHEEL_X", "REACTION_WHEEL_Y", "REACTION_WHEEL_Z", "GYRO_STAB", "MAG_FIELD_INT",
    "CPU_LOAD", "MEM_USAGE", "OS_INTEGRITY", "UPLINK_DBM", "DOWNLINK_BW",
    "THERMAL_SHIELD", "TRANS_CORE_TEMP", "ANTENNA_ALIGN", "S_BAND_STATUS", "X_BAND_FREQ",
    "OBC_HEALTH", "EPS_EFFICIENCY", "TTC_LATENCY", "ADCS_MODE", "AOCS_PRECISION",
    "PROP_PRESSURE", "FUEL_REMAIN", "THRUSTER_A_PSI", "THRUSTER_B_PSI", "PLD_STATUS",
    "IMG_BUFFER", "LENS_TEMP", "CCD_BIAS", "RAD_LEVEL", "STAR_TRACKER_1",
    "STAR_TRACKER_2", "HORIZON_SENS", "GPS_LOCK_VAL", "CLOCK_DRIFT", "MISSION_PHASE"
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
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # สร้างข้อมูล 40 รายการ
    full_tele = {
        "SAT_LAT": f"{subpoint.latitude.degrees:.4f}",
        "SAT_LON": f"{subpoint.longitude.degrees:.4f}",
        "SAT_ALT": f"{subpoint.elevation.km:.2f}",
        "SAT_VEL": f"{v_km_s * 3600:.2f}"
    }
    for label in TELEMETRY_LABELS:
        if label not in full_tele:
            full_tele[label] = f"{random.uniform(10.0, 99.9):.2f}"

    history = {"lats": [], "lons": [], "vels": [], "alts": []}
    for i in range(0, 101, 5):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        g = sat_obj.at(pt); s = wgs84.subpoint(g)
        history["lats"].append(s.latitude.degrees); history["lons"].append(s.longitude.degrees)
        history["vels"].append(np.linalg.norm(g.velocity.km_per_s) * 3600)
        history["alts"].append(s.elevation.km)
    return full_tele, history

class ULTIMATE_PDF(FPDF):
    def draw_detailed_graph(self, x, y, w, h, title, data, color):
        self.set_fill_color(245, 245, 245); self.rect(x, y, w, h, 'F')
        self.set_draw_color(0, 0, 0); self.set_line_width(0.3); self.rect(x, y, w, h)
        self.set_font("Arial", 'B', 9); self.set_xy(x, y-4); self.cell(w, 4, title)
        if len(data) > 1:
            min_v, max_v = min(data), max(data); v_range = (max_v - min_v) if max_v != min_v else 1
            pts = [(x + (i*(w/(len(data)-1))), (y+h) - ((v-min_v)/v_range*h*0.8) - (h*0.1)) for i,v in enumerate(data)]
            self.set_draw_color(*color); self.set_line_width(0.5)
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_ultimate_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m_main, m_hist):
    pdf = ULTIMATE_PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "OFFICIAL STRATEGIC ARCHIVE", ln=True, align='C')
    pdf.set_font("Arial", 'B', 8); addr_text = f"ZONE: {addr['z']} | COUNTRY: {addr['c']} | PROV: {addr['p']} | DIST: {addr['d']} | SUB: {addr['s']}"
    pdf.cell(0, 7, addr_text.upper(), border=1, ln=True, align='C')
    
    pdf.ln(5); pdf.set_font("Courier", 'B', 7)
    items = list(m_main.items())
    for i in range(0, 40, 4): # แสดงผล 40 รายการในตาราง PDF
        for j in range(4):
            if i+j < len(items):
                pdf.cell(47.5, 7, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    pdf.ln(5); pdf.draw_detailed_graph(10, 105, 190, 40, "ORBITAL LATITUDE TRACK", m_hist["lats"], (0, 100, 200))
    pdf.draw_detailed_graph(10, 155, 90, 35, "VELOCITY (KM/H)", m_hist["vels"], (200, 50, 0))
    pdf.draw_detailed_graph(110, 155, 90, 35, "ALTITUDE (KM)", m_hist["alts"], (0, 150, 50))
    
    pdf.set_draw_color(0,0,0); pdf.rect(15, 215, 40, 50)
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 17.5, 217, 35, 35)
    pdf.set_xy(15, 253); pdf.set_font("Arial", 'B', 7); pdf.cell(40, 5, "SECURE VERIFICATION", align='C', ln=True)
    pdf.set_x(15); pdf.cell(40, 4, f"ID: {f_id}", align='C')
    
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 220, 30, 20)
    pdf.line(120, 245, 190, 245); pdf.set_xy(120, 247); pdf.set_font("Arial", 'B', 10); pdf.cell(70, 5, s_name.upper(), align='C', ln=True)
    pdf.set_x(120); pdf.set_font("Arial", 'I', 8); pdf.cell(70, 5, s_pos.upper(), align='C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); out = BytesIO(); writer.write(out); return out.getvalue()

st.set_page_config(page_title="ZENITH V8.4", layout="wide")

if 'show_modal' not in st.session_state: st.session_state.show_modal = False
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None

with st.sidebar:
    st.header("🛰️ MISSION COMMAND")
    sel_sat = st.selectbox("ACTIVE ASSET", list(sat_catalog.keys()))
    p_a = st.selectbox("จังหวัด", list(LOC_DB.keys()))
    z_a, c_a, d_a, s_a = st.text_input("โซน", "Asia"), st.text_input("ประเทศ", "Thailand"), st.text_input("อำเภอ", "Mueang"), st.text_input("ตำบล", "That Choeng Chum")
    loc_info = LOC_DB.get(p_a); st_lat, st_lon, st_tz = loc_info["lat"], loc_info["lon"], loc_info["tz"]
    st.divider()
    z1 = st.slider("Tactical", 1, 18, 12, key="z1")
    z2 = st.slider("Global", 1, 10, 2, key="z2")
    z3 = st.slider("Station", 1, 18, 15, key="z3")
    if st.button("🧧 GENERATE REPORT", use_container_width=True, type="primary"):
        st.session_state.show_modal = True

@st.dialog("📋 MISSION DATA ARCHIVE")
def modal():
    if st.session_state.pdf_blob is None:
        mode = st.radio("Calculation", ["Live", "Predictive"], horizontal=True)
        t_target = None
        if mode == "Predictive":
            c1, c2 = st.columns(2); t_target = datetime.combine(c1.date_input("Date"), c2.time_input("Time")).replace(tzinfo=timezone.utc)
        s_name, s_pos = st.text_input("Signer"), st.text_input("Position")
        s_img = st.file_uploader("Seal PNG", type=['png'])
        if st.button("🚀 ENCRYPT & GENERATE"):
            fid = f"SEC-{random.randint(100,999)}-{datetime.now().strftime('%H%M')}"
            pwd = "".join([str(random.randint(0,9)) for _ in range(6)])
            m_main, m_hist = run_calculation(sat_catalog[sel_sat], t_target)
            addr = {"z": z_a, "c": c_a, "p": p_a, "d": d_a, "s": s_a}
            st.session_state.pdf_blob = build_ultimate_archive(sel_sat, addr, s_name, s_pos, s_img, fid, pwd, m_main, m_hist)
            st.session_state.fid, st.session_state.pwd = fid, pwd
            st.rerun()
    else:
        st.markdown(f'<div style="border:4px solid black; padding:20px; text-align:center;">ID: <h2 style="color:red;">{st.session_state.fid}</h2>PASS: <h1 style="letter-spacing:10px;">{st.session_state.pwd}</h1></div>', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD", st.session_state.pdf_blob, f"{st.session_state.fid}.pdf", use_container_width=True)
        if st.button("CLOSE"): st.session_state.show_modal = False; st.session_state.pdf_blob = None; st.rerun()

if st.session_state.show_modal: modal()

@st.fragment(run_every=1.0)
def main_dashboard():
    synced_time = (datetime.now(timezone.utc) + timedelta(hours=st_tz)).strftime("%H:%M:%S")
    st.markdown(f'<div style="text-align:center; background:white; border:5px solid black; border-radius:100px; padding:10px;"><span style="font-size:60px; font-weight:900;">{synced_time}</span><br>LOCATION: {p_a}</div>', unsafe_allow_html=True)
    if sat_catalog and sel_sat in sat_catalog:
        m_main, m_hist = run_calculation(sat_catalog[sel_sat])
        c = st.columns(3)
        c[0].metric("ALTITUDE", f"{m_main['SAT_ALT']} KM")
        c[1].metric("VELOCITY", f"{m_main['SAT_VEL']} KM/H")
        c[2].metric("POSITION", f"{m_main['SAT_LAT']}, {m_main['SAT_LON']}")
        
        m_cols = st.columns(3)
        def draw_map(lt, ln, zm, k, tl, tn):
            fig = go.Figure()
            if tl: fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(color='yellow')))
            fig.add_trace(go.Scattermapbox(lat=[float(lt)], lon=[float(ln)], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=float(lt), lon=float(ln)), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=350, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)
        
        with m_cols[0]: draw_map(m_main['SAT_LAT'], m_main['SAT_LON'], z1, "m1", m_hist["lats"], m_hist["lons"])
        with m_cols[1]: draw_map(m_main['SAT_LAT'], m_main['SAT_LON'], z2, "m2", m_hist["lats"], m_hist["lons"])
        with m_cols[2]: draw_map(st_lat, st_lon, z3, "m3", [], [])

        st.subheader("📊 40-PARAMETER STRATEGIC TELEMETRY")
        # แสดงผล 40 รายการในรูปแบบตาราง 4 คอลัมน์บนหน้าจอ
        df_display = pd.DataFrame([list(m_main.items())[i:i+4] for i in range(0, 40, 4)])
        st.table(df_display)

main_dashboard()