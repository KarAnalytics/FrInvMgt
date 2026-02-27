from fpdf import FPDF
import qrcode
from io import BytesIO
import tempfile
import os

def generate_pdf_labels(allocations):
    """
    Generates a PDF where each page is a 1.69x0.75 inch label.
    allocations: list of dicts with 'location_id', 'patientvisit_id', 'specimen_type'
    Returns: byte stream of the PDF file.
    """
    # 1.69 inches by 0.75 inches in millimeters: ~42.93 mm x 19.05 mm
    pdf = FPDF(orientation='L', unit='mm', format=(19.05, 42.93))
    pdf.set_auto_page_break(False)
    
    # Keep track of specimen numbering per patient-visit
    visit_specimen_counts = {}
    
    for alloc in allocations:
        loc_id = alloc['location_id']
        pv_id = alloc['patientvisit_id']
        sp_type = alloc['specimen_type']
        
        # Increment counter for this patient-visit + specimen type
        key = f"{pv_id}_{sp_type}"
        visit_specimen_counts[key] = visit_specimen_counts.get(key, 0) + 1
        sp_number = visit_specimen_counts[key]
        
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
        # Make the QR code 17x17 mm to fit inside the 19.05 mm height
        pdf.image(temp_img_path, x=1, y=1, w=17, h=17)
        
        # 2. Draw Text next to the QR code
        # We start X at 19 mm since QR takes up 1-18 mm
        pdf.set_font("helvetica", style="B", size=8)
        
        # Start text at x=19 mm, y=2 mm
        pdf.set_xy(19, 2)
        pdf.cell(w=0, h=4, text="160502", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("helvetica", size=7)
        pdf.set_xy(19, 6)
        pdf.cell(w=0, h=4, text=pv_id, new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_xy(19, 10)
        pdf.cell(w=0, h=4, text=f"{sp_type} {sp_number}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_xy(19, 14)
        pdf.cell(w=0, h=4, text=loc_id, new_x="LMARGIN", new_y="NEXT")
        
        # Cleanup temp file
        os.remove(temp_img_path)
        
    return bytes(pdf.output())
