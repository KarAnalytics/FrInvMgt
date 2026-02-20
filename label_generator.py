from fpdf import FPDF
import qrcode
from io import BytesIO
import tempfile
import os

def generate_pdf_labels(allocations):
    """
    Generates a PDF where each page is a 4x1 inch label.
    allocations: list of dicts with 'location_id', 'patientvisit_id', 'specimen_type'
    Returns: byte stream of the PDF file.
    """
    # 4 inches x 1 inch in millimeters: ~101.6 mm x 25.4 mm
    pdf = FPDF(orientation='L', unit='mm', format=(25.4, 101.6))
    pdf.set_auto_page_break(False)
    
    for alloc in allocations:
        loc_id = alloc['location_id']
        pv_id = alloc['patientvisit_id']
        sp_type = alloc['specimen_type']
        
        pdf.add_page()
        
        # 1. Generate QR code image temporarily to embed
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=1,
        )
        qr.add_data(loc_id)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save temp image
        temp_img_path = tempfile.mktemp(suffix=".png")
        img.save(temp_img_path)
        
        # Draw QR Code on the left side
        # image(name, x, y, w, h)
        # We make it 20x20 mm, vertically centered 
        pdf.image(temp_img_path, x=2, y=2.7, w=20, h=20)
        
        # 2. Draw Text next to it
        pdf.set_font("helvetica", style="B", size=10)
        
        # Start text at x=25 mm
        pdf.set_xy(25, 4)
        pdf.cell(w=0, h=5, text=f"ID: {loc_id}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("helvetica", size=9)
        pdf.set_xy(25, 10)
        pdf.cell(w=0, h=5, text=f"Patient-Visit: {pv_id}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_xy(25, 16)
        pdf.cell(w=0, h=5, text=f"Type: {sp_type}", new_x="LMARGIN", new_y="NEXT")
        
        # Cleanup temp file
        os.remove(temp_img_path)
        
    return bytes(pdf.output())
