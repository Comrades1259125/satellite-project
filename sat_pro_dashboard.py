import streamlit as st
import pandas as pd
from fpdf import FPDF
import qrcode
from io import BytesIO

# --- ฟังก์ชันสร้าง PDF ---
def build_pdf(sat_name, addr_data, s_name, s_pos, s_img, fid, pwd, m_data):
    pdf = FPDF()
    pdf.add_page()
    
    # ส่วนหัวรายงาน
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, "STRATEGIC MISSION ARCHIVE", ln=True, align='C')
    pdf.ln(10)
    
    # รายละเอียด
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, f"Satellite Name: {sat_name}", ln=True)
    pdf.cell(200, 10, f"Status: {s_name}", ln=True)
    pdf.cell(200, 10, f"Position: {s_pos}", ln=True)
    pdf.cell(200, 10, f"FID: {fid}", ln=True)
    pdf.ln(10)

    # สร้าง QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(f"SATELLITE:{sat_name}|FID:{fid}|PWD:{pwd}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # บันทึก QR Code ลงในหน่วยความจำ
    qr_buf = BytesIO()
    qr_img.save(qr_buf, format='PNG')
    
    # --- จุดที่เคยมีปัญหา: ใช้ไฟล์ชั่วคราวและย่อหน้าให้ตรงกัน ---
    with open("temp_qr.png", "wb") as f:
        f.write(qr_buf.getvalue())
    pdf.image("temp_qr.png", x=20, y=190, w=45, h=60)
    
    return pdf.output(dest='S').encode('latin-1')

# --- ส่วนของหน้าจอ Dashboard (ตัวอย่างโครงสร้างหลัก) ---
st.title("🛰️ Satellite Telemetry Archive")

# (ส่วนนี้คือโค้ดหน้าจอของคุณที่เหลือ... ผมรวบยอดให้ตรงจุดที่มีปัญหา)
# สมมติว่ามีการเรียกใช้ archive_dialog และ build_pdf
if st.button("EXECUTE REPORT"):
    # จำลองตัวแปร (ในโค้ดจริงของคุณจะมีค่าเหล่านี้อยู่แล้ว)
    try:
        pdf_bytes = build_pdf("SAT-1", "ADDR-01", "ACTIVE", "10.0, 20.0", "", "FID123", "PWD456", "DATA")
        st.success("Report Generated Successfully!")
        st.download_button("Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
    except Exception as e:
        st.error(f"Error: {e}")