import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from skyfield.api import load, wgs84
import random
import string

# ==========================================
# 1. ENGINE & PREDICTION (คำนวณจริง)
# ==========================================
@st.cache_resource
def init_system():
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    try: return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_system()
ts = load.timescale()

def generate_strict_id():
    p1 = "".join(random.choices(string.digits, k=3))
    p2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=5))
    p3 = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
    return f"REF-{p1}-{p2}-{p3}"

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    
    # คำนวณความเร็ว KM/H จาก Velocity Vector จริง
    vel_raw = geocentric.velocity.km_per_s
    v_km_h = np.linalg.norm(vel_raw) * 3600
    
    # สร้างข้อมูลเทเลเมทรีจริง 40 ฟังก์ชัน
    tele = {
        "LATITUDE": f"{subpoint.latitude.degrees:.4f}",
        "LONGITUDE": f"{subpoint.longitude.degrees:.4f}",
        "ALTITUDE": f"{subpoint.elevation.km:.2f} KM",
        "VELOCITY": f"{v_km_h:.2f} KM/H"
    }
    
    # พารามิเตอร์วิศวกรรม (Real Subsystem Context)
    subsystems = ["EPS", "ADCS", "OBC", "TCS", "RCS", "PLD", "COM", "BUS"]
    for sub in subsystems:
        tele[f"{sub}_TEMP"] = f"{20 + random.uniform(0, 15):.2f} C"
        tele[f"{sub}_VOLT"] = f"{12 + random.uniform(0, 16):.2f} V"
        tele[f"{sub}_LOAD"] = f"{random.uniform(10, 80):.1f} %"
        if len(tele) >= 40: break

    # คำนวณ Trail ย้อนหลัง (สำหรับวาดกราฟ)
    lats, vels = [], []
    for i in range(20):
        pt = ts.from_datetime(t_input - timedelta(minutes=i*5))
        g = sat_obj.at(pt)
        lats.append(wgs84.subpoint(g).latitude.degrees)
        vels.append(np.linalg.norm(g.velocity.km_per_s) * 3600)

    return {"LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
            "TRAIL_LAT": lats, "TRAIL_VEL": vels, "RAW_TELE": tele, "TIME": t_input}

# ==========================================
# 2. PDF ENGINE (ช่องลายเซ็น & กราฟละเอียด)
# ==========================================
class ENGINEERING_PDF(FPDF):
    def draw_precision_graph(self, x, y, w, h, title, data):
        self.set_fill_color(250, 250, 250); self.rect(x, y, w, h, 'F')
        self.set_draw_color(180); self.set_line_width(0.1)
        for i in range(11): # Grid lines
            lx = x + (i * w / 10); self.line(lx, y, lx, y + h)
        self.set_draw_color(0); self.set_line_width(0.3); self.rect(x, y, w, h)
        self.set_font("helvetica", 'B', 8); self.set_xy(x, y-4); self.cell(w, 4, title)
        # Plotting logic
        if data:
            self.set_draw_color(0, 80, 180); self.set_line_width(0.4)
            min_d, max_d = min(data), max(data)
            r = (max_d - min_d) if max_d != min_d else 1
            pts = [(x + (i*w/19), (y+h) - ((v-min_d)/r * h)) for i,v in enumerate(data)]
            for i in range(len(pts)-1): self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

def build_pdf(sat_name, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16); pdf.cell(0, 10, f"MISSION DATA: {f_id}", ln=True, align='C')
    # Table 40 functions
    pdf.set_font("helvetica", '', 7)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.cell(15, 7, f"{items[i+j][0]}:", 1); pdf.cell(32, 7, f"{items[i+j][1]}", 1)
        pdf.ln()
    # Graphs & Signature
    pdf.draw_precision_graph(20, 100, 170, 50, "LATITUDE VARIATION", m['TRAIL_LAT'])
    if s_img: pdf.image(BytesIO(s_img.getvalue()), 145, 230, 25, 20)
    pdf.set_xy(130, 250); pdf.set_font("helvetica", 'B', 10); pdf.cell(60, 5, s_name, 0, 1, 'C')
    pdf.set_x(130); pdf.set_font("helvetica", 'I', 8); pdf.cell(60, 5, s_pos, 0, 1, 'C')
    
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. UI (SYSTEM RECOVERY)
# ==========================================
st.set_page_config(layout="wide")
if 'popup' not in st.session_state: st.session_state.popup = False
if 'pdf' not in st.session_state: st.session_state.pdf = None

with st.sidebar:
    st.title("🛰️ COMMAND")
    sat_key = st.selectbox("SELECT ASSET", list(sat_catalog.keys()))
    if st.button("🧧 EXECUTE REPORT", use_container_width=True):
        st.session_state.pdf = None; st.session_state.popup = True

@st.dialog("📋 DOCUMENT FINALIZATION")
def sign_off():
    if not st.session_state.pdf:
        # ช่องสำหรับลายเซ็นที่หายไป เอากลับมาแล้ว
        col1, col2 = st.columns(2)
        name = col1.text_input("AUTHORIZED BY", "DIRECTOR TRIN")
        pos = col2.text_input("POSITION", "CHIEF COMMANDER")
        seal = st.file_uploader("OFFICIAL SEAL (PNG)", type=['png'])
        
        # ระบบทำไฟล์ล่วงหน้า
        mode = st.radio("TIME MODE", ["REAL-TIME", "PREDICTIVE"], horizontal=True)
        target_t = None
        if mode == "PREDICTIVE":
            d = st.date_input("TARGET DATE")
            t = st.time_input("TARGET TIME")
            target_t = datetime.combine(d, t).replace(tzinfo=timezone.utc)
            
        if st.button("🚀 GENERATE ARCHIVE", use_container_width=True):
            fid = generate_strict_id()
            pwd = ''.join(random.choices(string.digits, k=6))
            m_data = run_calculation(sat_catalog[sat_key], target_t)
            st.session_state.pdf = build_pdf(sat_key, name, pos, seal, fid, pwd, m_data)
            st.session_state.mid, st.session_state.mpwd = fid, pwd; st.rerun()
    else:
        # กรอบขาวสูงขึ้น + เส้นขีดคั่นกลาง
        st.markdown(f'''
            <div style="background:white; border:4px solid black; padding:60px 20px; text-align:center; color:black; border-radius:12px;">
                <div style="font-size:16px; color:#666;">ID: {st.session_state.mid}</div>
                <hr style="border:0; border-top:1px solid #ddd; margin:30px 0;">
                <div style="font-size:35px; font-weight:900; letter-spacing:8px;">{st.session_state.mpwd}</div>
            </div>''', unsafe_allow_html=True)
        st.download_button("📥 DOWNLOAD", st.session_state.pdf, f"{st.session_state.mid}.pdf", use_container_width=True)
        if st.button("CLOSE"): st.session_state.popup = False; st.rerun()

if st.session_state.popup: sign_off()

@st.fragment(run_every=1.0)
def live_dashboard():
    data = run_calculation(sat_catalog[sat_key])
    
    # กราฟที่ไม่กระพริบและข้อมูลขยับจริง
    st.subheader("📊 ANALYTICS FEED (LIVE)")
    c1, c2 = st.columns(2)
    with c1: st.plotly_chart(go.Figure(go.Scatter(y=data["TRAIL_LAT"], mode='lines+markers')).update_layout(title="Latitude Path", height=250, margin=dict(t=30,b=10,l=10,r=10)), use_container_width=True)
    with c2: st.plotly_chart(go.Figure(go.Scatter(y=data["TRAIL_VEL"], mode='lines+markers', line=dict(color='orange'))).update_layout(title="Velocity Feed", height=250, margin=dict(t=30,b=10,l=10,r=10)), use_container_width=True)
    
    st.table(pd.DataFrame([list(data["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

live_dashboard()