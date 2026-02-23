import streamlit as st
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timezone
from fpdf import FPDF 
from pypdf import PdfReader, PdfWriter
import qrcode
from io import BytesIO
from PIL import Image, ImageDraw

# ==========================================
# ADVANCED PDF ENGINE (OFFICIAL VERSION)
# ==========================================
class ENGINEERING_PDF(FPDF):
    def header(self):
        # พื้นหลังสีอ่อนเบาๆ ให้ดูเป็นเอกสารเทคนิค
        self.set_fill_color(250, 250, 252)
        self.rect(5, 5, 200, 287, 'D')

    def draw_precision_graph(self, x, y, w, h, title, data, color=(0, 70, 180), unit=""):
        # วาดตารางพื้นหลังกราฟ (Precision Grid) 
        self.set_fill_color(255, 255, 255)
        self.rect(x, y, w, h, 'F')
        
        # วาด Grid Lines แบบละเอียด 
        self.set_draw_color(230, 230, 235)
        self.set_line_width(0.1)
        for i in range(1, 11):
            # แนวตั้ง
            lx = x + (i * w / 10)
            self.line(lx, y, lx, y + h)
            # แนวนอน
            ly = y + (i * h / 10)
            self.line(x, ly, x + w, ly)

        # วาดกรอบนอกกราฟ
        self.set_draw_color(40, 45, 55)
        self.set_line_width(0.3)
        self.rect(x, y, w, h)

        # หัวข้อกราฟ
        self.set_font("helvetica", 'B', 9)
        self.set_text_color(50, 55, 65)
        self.set_xy(x, y - 6)
        self.cell(w, 5, f"{title.upper()} {unit}", align='L')

        # พล็อตข้อมูล (Line Plot)
        if len(data) > 1:
            min_v, max_v = min(data), max(data)
            v_range = (max_v - min_v) if max_v != min_v else 1
            
            # คำนวณจุดพิกัด
            pts = []
            for i, v in enumerate(data):
                px = x + (i * (w / (len(data) - 1)))
                py = (y + h) - ((v - min_v) / v_range * h * 0.8) - (h * 0.1)
                pts.append((px, py))

            # ลากเส้นข้อมูลให้สมูท
            self.set_draw_color(*color)
            self.set_line_width(0.6)
            for i in range(len(pts) - 1):
                self.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

            # แสดงค่า Max/Min ที่แกน 
            self.set_font("helvetica", '', 7)
            self.set_text_color(100, 100, 110)
            self.set_xy(x - 12, y)
            self.cell(10, 3, f"{max_v:.1f}", align='R')
            self.set_xy(x - 12, y + h - 3)
            self.cell(10, 3, f"{min_v:.1f}", align='R')

def generate_verified_qr(f_id):
    qr = qrcode.QRCode(border=1)
    qr.add_data(f"VERIFIED-ARCHIVE-ID:{f_id}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # เพิ่มกรอบและข้อความ Verified 
    canvas = Image.new('RGB', (img.size[0] + 20, img.size[1] + 40), 'white')
    draw = ImageDraw.Draw(canvas)
    canvas.paste(img, (10, 5))
    draw.text((canvas.size[0]/2, canvas.size[1]-15), "VERIFIED ARCHIVE", fill="black", anchor="mm")
    
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf

def build_pdf(sat_name, addr, s_name, s_pos, s_img, f_id, pwd, m):
    pdf = ENGINEERING_PDF()
    
    # --- PAGE 1: TELEMETRY DATA --- [cite: 1, 2, 3, 4]
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 22)
    pdf.set_text_color(20, 30, 50)
    pdf.cell(0, 20, "STRATEGIC MISSION ARCHIVE", ln=True, align='C') # [cite: 1]
    
    # ID Section
    pdf.set_font("helvetica", 'B', 12)
    pdf.set_text_color(100, 100, 110)
    pdf.cell(0, 8, f"ARCHIVE ID: {f_id}", ln=True, align='C') # [cite: 2]
    
    # Location Header
    pdf.set_fill_color(40, 45, 55)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", 'B', 9)
    loc_text = f"ASSET: {sat_name.upper()} | STATION: {addr['sub']}, {addr['dist']}, {addr['prov']}, {addr['cntr']}".upper()
    pdf.cell(0, 10, f"  {loc_text}", ln=True, fill=True) # [cite: 3]
    
    pdf.ln(5)
    
    # Telemetry Table (4 Columns Layout) 
    items = list(m['RAW_TELE'].items())
    pdf.set_text_color(40, 45, 55)
    for i in range(0, len(items), 4):
        for j in range(4):
            if i+j < len(items):
                key, val = items[i+j]
                pdf.set_font("helvetica", 'B', 7)
                pdf.set_fill_color(245, 245, 247)
                pdf.cell(47.5, 6, f" {key}", border='LTR', ln=0, fill=True)
        pdf.ln()
        for j in range(4):
            if i+j < len(items):
                key, val = items[i+j]
                pdf.set_font("helvetica", '', 8)
                pdf.cell(47.5, 7, f" {val}", border='LBR', ln=0)
        pdf.ln(2)

    # --- PAGE 2: ANALYTICS & SIGNATURE --- [cite: 5, 8, 9, 14, 15]
    pdf.add_page()
    pdf.draw_precision_graph(20, 30, 170, 70, "ORBITAL LATITUDE TRACKING", m['TAIL_LAT'], (0, 80, 180), "(DEG)") # [cite: 5]
    pdf.draw_precision_graph(20, 120, 80, 55, "VELOCITY", m['TAIL_VEL'], (180, 110, 0), "(KM/H)") # [cite: 8]
    pdf.draw_precision_graph(110, 120, 80, 55, "ALTITUDE", m['TAIL_ALT'], (0, 130, 70), "(KM)") # [cite: 9]
    
    # Footer Section (QR & Signature)
    qr_buf = generate_verified_qr(f_id)
    pdf.image(qr_buf, 20, 200, 40) # 
    
    # Signature Line
    pdf.set_draw_color(40, 45, 55)
    pdf.line(110, 240, 190, 240)
    
    if s_img:
        pdf.image(BytesIO(s_img.getvalue()), 140, 215, 30)
    
    pdf.set_xy(110, 242)
    pdf.set_font("helvetica", 'B', 12)
    pdf.cell(80, 7, s_name.upper(), align='C', ln=True) # 
    pdf.set_x(110)
    pdf.set_font("helvetica", 'I', 10)
    pdf.cell(80, 5, s_pos.upper(), align='C') # 

    # Encryption [cite: 2]
    raw = BytesIO(pdf.output())
    reader = PdfReader(raw)
    writer = PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.encrypt(pwd)
    
    final = BytesIO()
    writer.write(final)
    return final.getvalue()