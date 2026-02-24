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

# ==========================================
# 1. ระบบเครื่องยนต์ข้อมูล (Core Engine)
# ==========================================
@st.cache_resource
def init_satellite_system():
    try:
        url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        return {sat.name: sat for sat in load.tle_file(url)}
    except: return {}

sat_catalog = init_satellite_system()
ts = load.timescale()

def run_calculation(sat_obj, target_dt=None):
    t_input = target_dt if target_dt else datetime.now(timezone.utc)
    t = ts.from_datetime(t_input)
    geocentric = sat_obj.at(t)
    subpoint = wgs84.subpoint(geocentric)
    v_km_s = np.linalg.norm(geocentric.velocity.km_per_s)
    
    # ข้อมูลเทเลเมทรี 40 รายการ
    tele = {
        "TRK_LAT": f"{subpoint.latitude.degrees:.4f}",
        "TRK_LON": f"{subpoint.longitude.degrees:.4f}",
        "TRK_ALT": f"{subpoint.elevation.km:.2f} KM",
        "TRK_VEL": f"{v_km_s * 3600:,.2f} KM/H",
    }
    for i in range(36): tele[f"DATA_{i+1:02d}"] = f"{random.uniform(10, 99):.2f}"

    # เส้นทางโคจรย้อนหลัง 100 นาที (เส้นสีเหลือง)
    lats, lons = [], []
    for i in range(0, 101, 10):
        pt = ts.from_datetime(t_input - timedelta(minutes=i))
        ps = wgs84.subpoint(sat_obj.at(pt))
        lats.append(ps.latitude.degrees); lons.append(ps.longitude.degrees)

    return {
        "COORD": f"{subpoint.latitude.degrees:.4f}, {subpoint.longitude.degrees:.4f}",
        "LAT": subpoint.latitude.degrees, "LON": subpoint.longitude.degrees,
        "ALT_VAL": subpoint.elevation.km, "VEL_VAL": v_km_s * 3600,
        "TAIL_LAT": lats, "TAIL_LON": lons, "RAW_TELE": tele
    }

# ==========================================
# 2. ระบบสร้าง PDF และความปลอดภัย (PDF Engine)
# ==========================================
def build_archive(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "OFFICIAL MISSION ARCHIVE", ln=True, align='C')
    
    # ส่วนหัวที่อยู่ 5 ระดับ
    pdf.set_font("Arial", 'B', 8)
    addr_str = f"ZONE: {addr['z']} | COUNTRY: {addr['c']} | PROVINCE: {addr['p']} | DISTRICT: {addr['d']} | SUB: {addr['s']}"
    pdf.cell(0, 8, addr_str.upper(), border=1, ln=True, align='C')
    
    # ตารางข้อมูล 40 ช่อง
    pdf.ln(5)
    items = list(m['RAW_TELE'].items())
    for i in range(0, 40, 4):
        for j in range(4):
            if i+j < len(items):
                pdf.set_font("Courier", '', 7)
                pdf.cell(47.5, 8, f"{items[i+j][0]}: {items[i+j][1]}", border=1)
        pdf.ln()

    # QR Code และ ระบบลายเซ็น
    qr = qrcode.make(f_id).convert('RGB'); q_buf = BytesIO(); qr.save(q_buf, format="PNG")
    pdf.image(q_buf, 20, 230, 30, 30)
    
    if s_img: # ตราประทับ
        pdf.image(BytesIO(s_img.getvalue()), 140, 235, 30, 20)
    
    pdf.set_xy(110, 260); pdf.set_font("Arial", 'B', 10); pdf.cell(80, 5, s_name.upper(), align='C', ln=True)
    pdf.set_x(110); pdf.set_font("Arial", 'I', 8); pdf.cell(80, 5, s_pos.upper(), align='C')

    # ระบบเข้ารหัส PDF (รหัสผ่าน)
    raw = BytesIO(pdf.output()); reader = PdfReader(raw); writer = PdfWriter()
    for p in reader.pages: writer.add_page(p)
    writer.encrypt(pwd); final = BytesIO(); writer.write(final); return final.getvalue()

# ==========================================
# 3. ส่วนติดต่อผู้ใช้ (Interface)
# ==========================================
st.set_page_config(page_title="ZENITH COMMAND V7.7", layout="wide")

# ตั้งค่าสถานะเริ่มต้น (Session State)
if 'pdf_blob' not in st.session_state: st.session_state.pdf_blob = None
if 'open_sys' not in st.session_state: st.session_state.open_sys = False
if 'm_id' not in st.session_state: st.session_state.m_id = ""
if 'm_pwd' not in st.session_state: st.session_state.m_pwd = ""

with st.sidebar:
    st.header("🛰️ แผงควบคุมภารกิจ")
    sel_sat = st.selectbox("เลือกดาวเทียม", list(sat_catalog.keys()) if sat_catalog else ["กำลังโหลด..."])
    
    st.subheader("📍 ที่อยู่ติดตั้งสถานี")
    addr_data = {
        "z": st.text_input("โซน", "Asia"),
        "c": st.text_input("ประเทศ", "Thailand"),
        "p": st.text_input("จังหวัด", "Bangkok"),
        "d": st.text_input("อำเภอ", "Phra Nakhon"),
        "s": st.text_input("ตำบล", "Phra Borom")
    }

    st.divider()
    st.subheader("🔍 ระบบซูมแผนที่")
    z1 = st.slider("Tactical (ซูมใกล้)", 1, 18, 12)
    z2 = st.slider("Global (ซูมโลก)", 1, 10, 2)
    z3 = st.slider("Station (ซูมสถานี)", 1, 18, 15)
    
    # ปุ่มเปิดป๊อปอัพรายงาน
    if st.button("🧧 สร้างรายงานทางการ", use_container_width=True, type="primary"):
        st.session_state.open_sys = True

# ระบบป๊อปอัพ (Dialog) - รวมระบบลายเซ็น/รหัสผ่าน/คำนวณล่วงหน้า
if st.session_state.open_sys:
    @st.dialog("📋 การเข้าถึงจดหมายเหตุภารกิจ")
    def archive_dialog():
        if st.session_state.pdf_blob is None:
            # 1. ระบบคำนวณล่วงหน้า
            mode = st.radio("โหมดการคำนวณ", ["Live (ปัจจุบัน)", "Predictive (ล่วงหน้า)"], horizontal=True)
            t_sel = None
            if "Predictive" in mode:
                c1, c2 = st.columns(2)
                t_sel = datetime.combine(c1.date_input("วันที่"), c2.time_input("เวลา")).replace(tzinfo=timezone.utc)
            
            st.divider()
            # 2. ระบบลายเซ็นและตราประทับ
            s_name = st.text_input("ชื่อผู้ลงนาม (Signer)", "DIRECTOR TRIN")
            s_pos = st.text_input("ตำแหน่ง (Designation)", "CHIEF COMMANDER")
            s_img = st.file_uploader("อัปโหลดตราประทับ (Seal PNG)", type=['png'])
            
            # 3. ปุ่มสร้างไฟล์และรหัสผ่าน
            if st.button("ยืนยันการสร้างไฟล์และเข้ารหัส"):
                fid = f"REF-{random.randint(100,999)}-{datetime.now().strftime('%m%d')}"
                pwd = "".join([str(random.randint(0,9)) for _ in range(6)]) # สุ่มรหัสผ่าน 6 หลัก
                m_data = run_calculation(sat_catalog[sel_sat], t_sel)
                st.session_state.pdf_blob = build_archive(sel_sat, addr_data, s_name, s_pos, s_img, fid, pwd, m_data)
                st.session_state.m_id = fid
                st.session_state.m_pwd = pwd
                st.rerun()
        else:
            # แสดงรหัสผ่านและปุ่มดาวน์โหลด
            st.success(f"ID: {st.session_state.m_id}")
            st.warning(f"PASSWORD: {st.session_state.m_pwd}")
            st.download_button("📥 ดาวน์โหลดไฟล์ PDF (ENCRYPTED)", st.session_state.pdf_blob, f"{st.session_state.m_id}.pdf", use_container_width=True)
            if st.button("ปิดหน้าต่าง"):
                st.session_state.open_sys = False
                st.session_state.pdf_blob = None
                st.rerun()
    archive_dialog()

# ส่วนการแสดงผลหลัก (Main Dashboard)
@st.fragment(run_every=1.0)
def dashboard():
    # นาฬิกาดิจิทัล
    st.markdown(f'''<div style="text-align:center; background:white; border:5px solid black; padding:10px; border-radius:100px; margin-bottom:20px;">
                <span style="color:black; font-size:50px; font-weight:900; font-family:monospace;">{datetime.now().strftime("%H:%M:%S")}</span></div>''', unsafe_allow_html=True)
    
    if sat_catalog and sel_sat in sat_catalog:
        m = run_calculation(sat_catalog[sel_sat])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("ระดับความสูง", f"{m['ALT_VAL']:,.2f} KM")
        c2.metric("ความเร็วโคจร", f"{m['VEL_VAL']:,.0f} KM/H")
        c3.metric("พิกัดปัจจุบัน", m["COORD"])
        
        # แสดงแผนที่ 3 ช่องพร้อมเส้นทาง (Yellow Lines)
        st.subheader("🌍 การวิเคราะห์ตำแหน่งทางภูมิศาสตร์")
        m_cols = st.columns(3)
        
        def draw_map(lt, ln, zm, k, tl, tn):
            fig = go.Figure()
            if tl: # วาดเส้นทางสีเหลือง
                fig.add_trace(go.Scattermapbox(lat=tl, lon=tn, mode='lines', line=dict(width=3, color='yellow')))
            fig.add_trace(go.Scattermapbox(lat=[lt], lon=[ln], mode='markers', marker=dict(size=15, color='red')))
            fig.update_layout(mapbox=dict(style="white-bg", layers=[{"below": 'traces', "sourcetype": "raster", "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"]}], center=dict(lat=lt, lon=ln), zoom=zm), margin=dict(l=0,r=0,t=0,b=0), height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=k)

        with m_cols[0]: draw_map(m['LAT'], m['LON'], z1, "T1", m["TAIL_LAT"], m["TAIL_LON"])
        with m_cols[1]: draw_map(m['LAT'], m['LON'], z2, "G1", m["TAIL_LAT"], m["TAIL_LON"])
        with m_cols[2]: draw_map(13.75, 100.5, z3, "S1", [], []) # สถานีภาคพื้นดิน

        st.subheader("📊 ข้อมูลเทเลเมทรี (40 รายการ)")
        st.table(pd.DataFrame([list(m["RAW_TELE"].items())[i:i+4] for i in range(0, 40, 4)]))

dashboard()