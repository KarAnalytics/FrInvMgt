import streamlit as st
import pandas as pd
import qrcode
from PIL import Image
from io import BytesIO
import database
import auth
from streamlit_cookies_manager import EncryptedCookieManager
import io
import label_generator
import cv2
import numpy as np
from pyzbar.pyzbar import decode

st.set_page_config(page_title="Freezer Inventory Management", layout="wide")

cookies = EncryptedCookieManager(prefix="freezer_app/", password="some_very_secret_password_here")
if not cookies.ready():
    st.stop()

database.init_db()

if "user" not in st.session_state:
    st.session_state["user"] = None

    stored_email = cookies.get("user_email")
    if stored_email:
        db_user = database.get_user(stored_email)
        if db_user and db_user['status'] == 'approved':
            st.session_state["user"] = db_user
        else:
            del cookies["user_email"]
            cookies.save()

def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def login_screen():
    st.title("Freezer Inventory Login")

    tab1, tab2, tab3 = st.tabs(["Login", "Register", "Forgot Password"])

    with tab1:
        st.subheader("Sign In")
        email_in = st.text_input("Email", key="login_email").strip()
        pwd_in = st.text_input("Password", type="password", key="login_pwd")
        remember_me = st.checkbox("Remember me on this device", value=True)
        
        if st.button("Log In"):
            user = database.get_user(email_in)
            if user:
                if user['status'] != 'approved':
                    st.error("Account pending admin approval.")
                elif user['password'] == pwd_in:
                    st.session_state["user"] = user
                    if remember_me:
                        cookies["user_email"] = user['email']
                        cookies.save()
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid password")
            else:
                st.error("User not found.")

    with tab2:
        st.subheader("Register")
        email_reg = st.text_input("Email", key="reg_email").strip()
        if st.button("Request Access"):
            if email_reg:
                success, msg = database.add_pending_user(email_reg)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.error("Please enter an email.")

    with tab3:
        st.subheader("Forgot Password")
        st.markdown("If approved, an email with your password will be sent to you.")
        email_forgot = st.text_input("Email", key="forgot_email").strip()
        if st.button("Send Recovery Email"):
            if email_forgot:
                user = database.get_user(email_forgot)
                if user and user['status'] == 'approved':
                    success, email_msg = auth.simulate_email(
                        to_email=user['email'],
                        subject="Password Recovery",
                        body=f"Your password is: {user['password']}"
                    )
                    if success:
                        st.success("Recovery Email Sent!")
                    else:
                        st.warning(email_msg)
                else:
                    st.error("Email not found or not approved.")
            else:
                st.error("Please enter email.")

def main():
    if st.session_state["user"] is None:
        login_screen()
        return

    user_role = st.session_state["user"]["role"]
    st.sidebar.title("Freezer Management")
    st.sidebar.write(f"Logged in as: **{st.session_state['user']['email']}**")
    
    if st.sidebar.button("Log Out"):
        st.session_state["user"] = None
        if "user_email" in cookies:
            del cookies["user_email"]
            cookies.save()
        st.rerun()

    nav_options = ["Dashboard", "Store Aliquots", "Scan/Toggle Aliquots", "User Guide"]
    if user_role == 'master':
        nav_options.append("Admin Panel")

    page = st.sidebar.radio("Navigation", nav_options)

    if page == "Dashboard":
        show_dashboard(user_role)
    elif page == "Store Aliquots":
        show_store_aliquots()
    elif page == "Scan/Toggle Aliquots":
        show_scan_aliquots()
    elif page == "User Guide":
        show_user_guide()
    elif page == "Admin Panel" and user_role == 'master':
        show_admin_panel()

def show_user_guide():
    st.header("Documentation")
    try:
        with open("user_guide.md", "r", encoding="utf-8") as f:
            content = f.read()
        st.markdown(content, unsafe_allow_html=True)
    except Exception as e:
        st.error("Could not load user guide. Ensure `user_guide.md` exists in the repository.")

def show_admin_panel():
    st.header("Admin Panel")
    st.write("Manage users and access.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Pending Approvals")
        pending = database.get_pending_users()
        if not pending:
            st.info("No pending users.")
        else:
            for em in pending:
                with st.expander(f"Review: {em}"):
                    if st.button(f"Approve {em}", key=f"app_{em}"):
                        new_pwd = auth.generate_password()
                        database.approve_user(em, new_pwd)
                        success, email_msg = auth.simulate_email(em, "Registration Approved", f"Your new password is: {new_pwd}")
                        st.success(f"Approved {em}!")
                        if not success:
                            st.warning(email_msg)
                        st.rerun()

    with col2:
        st.subheader("Add User Directly")
        with st.form("add_user"):
            new_em = st.text_input("Email").strip()
            if st.form_submit_button("Add Approved User"):
                if new_em:
                    new_pwd = auth.generate_password()
                    success, msg = database.add_approved_user(new_em, new_pwd)
                    if success:
                        email_succ, email_msg = auth.simulate_email(new_em, "Account Created", f"Your password is: {new_pwd}")
                        st.success("User added.")
                        if not email_succ:
                            st.warning(email_msg)
                    else:
                        st.error(msg)
                else:
                    st.error("Please enter an email.")

    st.markdown("---")
    st.subheader("Manage Existing Users")
    df = database.get_all_users()
    st.dataframe(df, use_container_width=True)

    with st.expander("Update Password or Remove User", expanded=False):
        c_mode = st.radio("Action", ["Change Password", "Remove User"])
        mgmt_email = st.text_input("Target Email").strip()
        
        if c_mode == "Change Password":
            opt_pwd = st.text_input("New Password (Leave blank to auto-generate)")
            if st.button("Update Password"):
                if mgmt_email:
                    target_user = database.get_user(mgmt_email)
                    if target_user:
                        pwd_to_set = opt_pwd if opt_pwd else auth.generate_password()
                        database.change_password(mgmt_email, pwd_to_set)
                        email_succ, email_msg = auth.simulate_email(mgmt_email, "Password Changed", f"Your new password: {pwd_to_set}")
                        st.success("Password Updated.")
                        if not email_succ:
                            st.warning(email_msg)
                    else:
                        st.error("User not found.")

        elif c_mode == "Remove User":
            if st.button("Delete User", type="primary"):
                if mgmt_email:
                    succ, msg = database.remove_user(mgmt_email)
                    if succ:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.error("Provide email.")

def show_dashboard(user_role):
    st.header("Freezer Overview")
    stats = database.get_freezer_stats()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Capacity (Boxes)", stats['total_boxes'])
    col2.metric("Boxes In Use", stats['active_boxes'])
    col3.metric("Empty Boxes", stats['empty_boxes'])
    
    col4, col5 = st.columns(2)
    col4.metric("Total Aliquots Stored", stats['total_aliquots_stored'])
    col5.metric("Total Aliquots Checked Out", stats['total_aliquots_checked_out'])
    
    st.subheader("Current Stored Aliquots by Type")
    if stats['type_counts_stored']:
        for tp, count in stats['type_counts_stored'].items():
            st.write(f"- **{tp}**: {count}")
    else:
        st.write("No aliquots stored yet.")
    
    st.markdown("---")
    if user_role == 'master':
        st.subheader("Complete Inventory Database (Admin View)")
    else:
        st.subheader("Recent Activity (User View)")
        
    full_df = database.get_all_aliquots_df()
    
    if full_df.empty:
        st.info("No aliquots found in the database.")
    else:
        if user_role == 'master':
            if not full_df.empty:
                full_df.index = range(1, len(full_df) + 1)
            st.dataframe(full_df, use_container_width=True)
            
            csv = full_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Full Inventory CSV",
                data=csv,
                file_name='freezer_inventory.csv',
                mime='text/csv',
            )
            
            st.markdown("---")
            st.subheader("Upload/Merge Inventory Data")
            st.markdown("Uploading a CSV with identical `Location ID` values will overwrite their details. New distinct locations are inserted securely.")
            uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
            if uploaded_file is not None:
                try:
                    df_up = pd.read_csv(uploaded_file)
                    st.write("Preview of Upload:")
                    st.dataframe(df_up.head())
                    if st.button("Merge into Database"):
                        df_up = df_up.fillna('')
                        succ, msg = database.upload_aliquots_data(df_up)
                        if succ:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"Error reading file: {e}")
        else:
            user_email = st.session_state["user"]["email"]
            # get_recent_aliquots returns a dataframe. 
            recent_df = database.get_recent_aliquots(user_email, 20)
            if not recent_df.empty:
                # Use a simple sequential row number as the index
                recent_df.index = range(1, len(recent_df) + 1)
            st.dataframe(recent_df, use_container_width=True)

def show_store_aliquots():
    st.header("Store New Aliquots")
    st.markdown("Enter a unique **Patient-Visit ID** string (e.g., `P001-V1`, `12345_1`). This identifies both the patient and the visit.")
    
    patientvisit_id = st.text_input("Patient-Visit ID")
    
    st.subheader("Specify Quantities (Max 10 per type)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        num_plasma = st.number_input("Plasma", min_value=0, max_value=10, value=0)
    with col2:
        num_serum = st.number_input("Serum", min_value=0, max_value=10, value=0)
    with col3:
        num_urine = st.number_input("Urine", min_value=0, max_value=10, value=0)
        
    if st.button("Allocate Spots & Generate Labels"):
        if not patientvisit_id.strip():
            st.error("Please enter a valid Patient-Visit ID.")
            return
            
        if num_plasma == 0 and num_serum == 0 and num_urine == 0:
            st.error("Please enter at least one aliquot.")
            return
            
        try:
            allocations = []
            user_email = st.session_state["user"]["email"]
            if num_plasma > 0:
                allocations.extend(database.allocate_aliquots(patientvisit_id.strip(), "Plasma", num_plasma, user_email))
            if num_serum > 0:
                allocations.extend(database.allocate_aliquots(patientvisit_id.strip(), "Serum", num_serum, user_email))
            if num_urine > 0:
                allocations.extend(database.allocate_aliquots(patientvisit_id.strip(), "Urine", num_urine, user_email))
                
            st.success(f"Successfully allocated {len(allocations)} aliquots!")
            
            # --- LABEL DOWNLOADING ---
            pdf_bytes = label_generator.generate_pdf_labels(allocations)
            st.download_button(
                label="🖨️ Download 4x1 PDF Printer Labels",
                data=pdf_bytes,
                file_name=f"labels_{patientvisit_id}.pdf",
                mime="application/pdf",
                type="primary"
            )
            st.markdown("---")
            
            st.subheader("Generated Labels")
            cols = st.columns(3)
            for i, alloc in enumerate(allocations):
                loc_id = alloc['location_id']
                spec_type = alloc['specimen_type']
                pvid = alloc['patientvisit_id']
                
                qr_content = f"{loc_id}"
                qr_img = generate_qr(qr_content)
                
                col = cols[i % 3]
                with col:
                    st.image(qr_img, width=150)
                    st.markdown(f"**Location ID:** {loc_id}<br>**Type:** {spec_type}<br>**Patient-Visit ID:** {pvid}", unsafe_allow_html=True)
                    st.markdown("---")
                    
        except Exception as e:
            st.error(f"Allocation Error: {e}")

def show_scan_aliquots():
    st.header("Scan/Toggle Aliquots")
    st.markdown("Use a QR Scanner, manually type the Aliquot Location ID below, or use the camera to scan a QR code.")
    st.markdown("Scanning an item that is `Stored` will mark it as `Checked Out`. Scanning it again will check it back into storage.")
    
    # Camera/Image Input for QR Scanning
    camera_image = st.camera_input("📷 Scan QR Code with Live Camera")
    uploaded_image = st.file_uploader("📁 Or upload/take a photo of a QR Code (Better for mobile)", type=['png', 'jpg', 'jpeg'])
    
    scanned_loc_id = ""
    image_to_process = camera_image if camera_image else uploaded_image
    
    if image_to_process is not None:
        try:
            # Convert the uploaded image to an OpenCV image
            file_bytes = np.asarray(bytearray(image_to_process.read()), dtype=np.uint8)
            opencv_image = cv2.imdecode(file_bytes, 1)
            
            # Decode the QR code
            decoded_objects = decode(opencv_image)
            if decoded_objects:
                scanned_loc_id = decoded_objects[0].data.decode("utf-8")
                st.success(f"Successfully scanned QR Code: **{scanned_loc_id}**")
            else:
                st.warning("No QR code detected in the image. Please try again or ensure the QR code is clearly visible.")
        except Exception as e:
            st.error(f"Error processing image for QR code: {e}")

    with st.form("scan_form", clear_on_submit=True):
        # Pre-fill with scanned ID if available
        loc_id = st.text_input("Aliquot Location ID (e.g. D1R1L1B1X1Y1)", value=scanned_loc_id)
        sent_to = st.text_input("Destination (optional, if checking out)")
        submitted = st.form_submit_button("Submit / Checkout")
        
        if submitted:
            if loc_id:
                user_email = st.session_state["user"]["email"]
                success, msg, new_status = database.toggle_aliquot_status(loc_id.strip().upper(), user_email, sent_to.strip())
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.error("Please enter or scan an ID.")

if __name__ == "__main__":
    main()
