import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import re
from datetime import datetime

# IMPORTANT: You must setup your .streamlit/secrets.toml with your Google Service Account
# and provide `spreadsheet` URL inside the `[connections.gsheets]` block.

def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=120, show_spinner=False)
def get_sheet_data(sheet_name):
    conn = get_connection()
    try:
        # ttl=0 forces the GSheetsConnection to bypass its own cache, 
        # so that our explicit @st.cache_data decorator manages it completely.
        df = conn.read(worksheet=sheet_name, ttl=0) 
        return pd.DataFrame(df)
    except Exception as e:
        return pd.DataFrame()

def write_sheet_data(sheet_name, df):
    conn = get_connection()
    # Write the dataframe back, completely replacing the current sheet data
    conn.update(worksheet=sheet_name, data=df)
    # Clear ONLY the cache for this specific sheet, saving API calls on the other sheets
    get_sheet_data.clear(sheet_name)

def init_db():
    if 'db_initialized' in st.session_state:
        return
        
    st.session_state['db_initialized'] = True
    # Because Google Sheets must be created manually and shared with the Service Account,
    # we cannot "create" tables out of nowhere. We assume the worksheets "users", "boxes", and "aliquots" 
    # already exist in the connected spreadsheet document.
    
    # 1. Initialize Users Sheet
    df_users = get_sheet_data("users")
    if df_users.empty or 'email' not in df_users.columns:
        # Create base dataframe
        df_users = pd.DataFrame({
            "email": ["kartucson@gmail.com"],
            "password": ["master123"],
            "role": ["master"],
            "status": ["approved"],
            "checkin_count": [0],
            "checkout_count": [0]
        })
        write_sheet_data("users", df_users)
    
    # 2. Initialize Boxes Sheet
    df_boxes = get_sheet_data("boxes")
    if df_boxes.empty or 'id' not in df_boxes.columns:
        box_data = []
        box_id = 1
        for d in range(1, 6):      
            for r in range(1, 5):  
                for l in range(1, 6): 
                    for b in range(1, 6): 
                        box_data.append({
                            "id": box_id,
                            "door_num": d,
                            "rack_num": r,
                            "level_num": l,
                            "box_num": b,
                            "specimen_type": "",
                            "spots_used": 0
                        })
                        box_id += 1
        df_boxes = pd.DataFrame(box_data)
        write_sheet_data("boxes", df_boxes)
        
    # 3. Initialize Aliquots Sheet
    df_aliquots = get_sheet_data("aliquots")
    if df_aliquots.empty or 'id' not in df_aliquots.columns:
        df_aliquots = pd.DataFrame(columns=[
            "id", "location_id", "box_id", "x_coord", "y_coord", 
            "patientvisit_id", "specimen_type", "status",
            "sent_to", "stored_time", "days_since_stored",
            "checkout_time", "checkin_user_id", "checkout_user_id"
        ])
        write_sheet_data("aliquots", df_aliquots)

# --- Auth Methods ---

def get_user(email):
    df = get_sheet_data("users")
    user_row = df[df['email'] == email]
    if not user_row.empty:
        u = user_row.iloc[0]
        return {'email': u['email'], 'password': u['password'], 'role': u['role'], 'status': u['status']}
    return None

def add_pending_user(email):
    df = get_sheet_data("users")
    if email in df['email'].values:
        return False, "Email already registered or pending."
        
    new_user = pd.DataFrame({
        "email": [email],
        "password": [""],
        "role": ["user"],
        "status": ["pending"],
        "checkin_count": [0],
        "checkout_count": [0]
    })
    df = pd.concat([df, new_user], ignore_index=True)
    write_sheet_data("users", df)
    return True, "Registration requested. Pending admin approval."

def approve_user(email, password):
    df = get_sheet_data("users")
    idx = df[df['email'] == email].index
    if not idx.empty:
        df.loc[idx, 'status'] = 'approved'
        df.loc[idx, 'password'] = password
        write_sheet_data("users", df)

def add_approved_user(email, password):
    df = get_sheet_data("users")
    if email in df['email'].values:
        return False, "Email already exists."
        
    new_user = pd.DataFrame({
        "email": [email],
        "password": [password],
        "role": ["user"],
        "status": ["approved"],
        "checkin_count": [0],
        "checkout_count": [0]
    })
    df = pd.concat([df, new_user], ignore_index=True)
    write_sheet_data("users", df)
    return True, "User added directly."

def change_password(email, new_password):
    df = get_sheet_data("users")
    idx = df[df['email'] == email].index
    if not idx.empty:
        df.loc[idx, 'password'] = new_password
        write_sheet_data("users", df)

def remove_user(email):
    if email == 'kartucson@gmail.com':
        return False, "Cannot delete master user."
    df = get_sheet_data("users")
    df = df[df['email'] != email]
    write_sheet_data("users", df)
    return True, f"User {email} removed."

def get_pending_users():
    df = get_sheet_data("users")
    pending = df[df['status'] == 'pending']
    return pending['email'].tolist()

def get_all_users():
    df = get_sheet_data("users")
    return df[['email', 'role', 'status']]

# --- Inventory Methods ---

def extract_patient_id(pv_id):
    for delim in ['-', '_', ' ']:
        if delim in pv_id:
            return pv_id.rsplit(delim, 1)[0]
    m = re.match(r"^(.*?)(\d+)$", pv_id)
    if m:
        return m.group(1)
    return pv_id

def allocate_aliquots(patientvisit_id, aliquot_type, count, user_email):
    if count <= 0:
        return []

    df_boxes = get_sheet_data("boxes")
    # Convert types just in case Google Sheets read them as strings
    df_boxes['id'] = pd.to_numeric(df_boxes['id'])
    df_boxes['spots_used'] = pd.to_numeric(df_boxes['spots_used'])
    
    df_aliquots = get_sheet_data("aliquots")
    if not df_aliquots.empty:
        df_aliquots['box_id'] = pd.to_numeric(df_aliquots['box_id'])
    
    # 1. Find a box (Constraint 3)
    target_box_id = None
    spots_used_in_target = 0
    
    if not df_aliquots.empty:
        # Check if already using a box for this specific PV and type
        matching = df_aliquots[(df_aliquots['patientvisit_id'] == patientvisit_id) & (df_aliquots['specimen_type'] == aliquot_type)]
        if not matching.empty:
            possible_box = matching.iloc[0]['box_id']
            b_row = df_boxes[df_boxes['id'] == possible_box]
            if not b_row.empty:
                used = b_row.iloc[0]['spots_used']
                if (81 - used) >= count:
                    target_box_id = possible_box
                    spots_used_in_target = used

    # Constraints 1 and 2
    if target_box_id is None:
        pat_id = extract_patient_id(patientvisit_id)
        
        forbidden_boxes = set()
        if not df_aliquots.empty:
            for _, row in df_aliquots.iterrows():
                pvid = row['patientvisit_id']
                if pvid != patientvisit_id and extract_patient_id(pvid) == pat_id:
                    forbidden_boxes.add(row['box_id'])
                    
        preferred_rack = None
        if aliquot_type == "Plasma":
            preferred_rack = 1
        elif aliquot_type == "Serum":
            preferred_rack = 2
        elif aliquot_type == "Urine":
            preferred_rack = 3
            
        def find_box(iterator):
            for _, row in iterator:
                b_id = row['id']
                if b_id in forbidden_boxes:
                    continue
                    
                s_type = str(row['specimen_type']).strip()
                if s_type == "" or s_type == "nan" or s_type == "None":
                    s_type = None
                    
                used = row['spots_used']
                
                if (s_type is None or s_type == aliquot_type) and (81 - used) >= count:
                    return b_id, used
            return None, 0
            
        # Pass 1: Try preferred rack exclusively
        if preferred_rack is not None:
            target_box_id, spots_used_in_target = find_box(
                df_boxes[(df_boxes['rack_num'] == preferred_rack) | (df_boxes['rack_num'] == str(preferred_rack))].iterrows()
            )
            
        # Pass 2: Fallback to Overflow Rack 4
        if target_box_id is None:
            target_box_id, spots_used_in_target = find_box(
                df_boxes[(df_boxes['rack_num'] == 4) | (df_boxes['rack_num'] == '4')].iterrows()
            )
            
        # Pass 3: Emergency Fallback to any rack anywhere in the freezer
        if target_box_id is None:
            target_box_id, spots_used_in_target = find_box(df_boxes.iterrows())
                
    if target_box_id is None:
        raise Exception(f"No suitable box found for allocation of {count} {aliquot_type} aliquots!")
        
    # 2. Find empty spots
    used_spots = set()
    if not df_aliquots.empty:
        box_aliq = df_aliquots[df_aliquots['box_id'] == target_box_id]
        for _, row in box_aliq.iterrows():
            used_spots.add((int(row['x_coord']), int(row['y_coord'])))
            
    empty_spots = []
    for x in range(1, 10):
        for y in range(1, 10):
            if (x, y) not in used_spots:
                empty_spots.append((x, y))
                
    spots_to_use = empty_spots[:count]
    
    # 3. Make IDs
    box_row = df_boxes[df_boxes['id'] == target_box_id].iloc[0]
    d, r, l, b = box_row['door_num'], box_row['rack_num'], box_row['level_num'], box_row['box_num']
    
    # Generate new aliquot ID index
    next_id = 1
    if not df_aliquots.empty:
        df_aliquots['id'] = pd.to_numeric(df_aliquots['id'])
        next_id = int(df_aliquots['id'].max()) + 1
        
    new_rows = []
    allocated = []
    curr_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for (x, y) in spots_to_use:
        location_id = f"D{d}R{r}L{l}B{b}X{x}Y{y}"
        new_rows.append({
            "id": next_id,
            "location_id": location_id,
            "box_id": target_box_id,
            "x_coord": x,
            "y_coord": y,
            "patientvisit_id": patientvisit_id,
            "specimen_type": aliquot_type,
            "status": "Stored",
            "sent_to": "",
            "stored_time": curr_time,
            "days_since_stored": 0,
            "checkout_time": "",
            "checkin_user_id": user_email,
            "checkout_user_id": ""
        })
        allocated.append({
            'location_id': location_id,
            'x': x,
            'y': y,
            'patientvisit_id': patientvisit_id,
            'specimen_type': aliquot_type
        })
        next_id += 1
        
    df_aliquots = pd.concat([df_aliquots, pd.DataFrame(new_rows)], ignore_index=True)
    write_sheet_data("aliquots", df_aliquots)
    
    # 4. Update box metadata
    idx = df_boxes[df_boxes['id'] == target_box_id].index
    df_boxes.loc[idx, 'spots_used'] = spots_used_in_target + count
    df_boxes.loc[idx, 'specimen_type'] = aliquot_type
    write_sheet_data("boxes", df_boxes)
    
    # 5. Update user checkin count
    df_users = get_sheet_data("users")
    u_idx = df_users[df_users['email'] == user_email].index
    if not u_idx.empty:
        df_users['checkin_count'] = pd.to_numeric(df_users['checkin_count'], errors='coerce').fillna(0)
        df_users.loc[u_idx, 'checkin_count'] += count
        write_sheet_data("users", df_users)
    
    return allocated

def toggle_aliquot_status(location_id, user_email, sent_to=""):
    df = get_sheet_data("aliquots")
    if df.empty:
        return False, "Aliquot not found.", None
        
    matches = df[df['location_id'] == location_id]
    if matches.empty:
        return False, "Aliquot not found.", None
        
    # Get highest ID index for this location
    matches['id'] = pd.to_numeric(matches['id'])
    latest_idx = matches['id'].idxmax()
    
    curr_status = df.loc[latest_idx, 'status']
    new_status = 'Checked Out' if curr_status == 'Stored' else 'Stored'
    
    curr_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    df_users = get_sheet_data("users")
    u_idx = df_users[df_users['email'] == user_email].index
    if not u_idx.empty:
        df_users['checkin_count'] = pd.to_numeric(df_users.get('checkin_count', 0), errors='coerce').fillna(0)
        df_users['checkout_count'] = pd.to_numeric(df_users.get('checkout_count', 0), errors='coerce').fillna(0)

    if new_status == 'Checked Out':
        df.loc[latest_idx, 'checkout_time'] = curr_time
        df.loc[latest_idx, 'checkout_user_id'] = user_email
        df.loc[latest_idx, 'sent_to'] = sent_to
        if not u_idx.empty:
            df_users.loc[u_idx, 'checkout_count'] += 1
    else:
        df.loc[latest_idx, 'stored_time'] = curr_time
        df.loc[latest_idx, 'checkin_user_id'] = user_email
        df.loc[latest_idx, 'checkout_time'] = ""
        df.loc[latest_idx, 'checkout_user_id'] = ""
        df.loc[latest_idx, 'sent_to'] = ""
        if not u_idx.empty:
            df_users.loc[u_idx, 'checkin_count'] += 1
            
    df.loc[latest_idx, 'status'] = new_status
    write_sheet_data("aliquots", df)
    if not u_idx.empty:
        write_sheet_data("users", df_users)
    
    return True, f"Aliquot toggled successfully. New Status: **{new_status}**", new_status

def get_freezer_stats():
    df_boxes = get_sheet_data("boxes")
    df_aliquots = get_sheet_data("aliquots")
    
    if df_boxes.empty:
        return {
            'total_boxes': 0, 'active_boxes': 0, 'empty_boxes': 0,
            'total_aliquots_stored': 0, 'total_aliquots_checked_out': 0, 'type_counts_stored': {}
        }
    
    df_boxes['spots_used'] = pd.to_numeric(df_boxes['spots_used'], errors='coerce').fillna(0)
    active_boxes = len(df_boxes[df_boxes['spots_used'] > 0])
    total_boxes = len(df_boxes)
    
    if df_aliquots.empty:
        total_stored = 0
        total_checked_out = 0
        type_counts = {}
    else:
        total_stored = len(df_aliquots[df_aliquots['status'] == 'Stored'])
        total_checked_out = len(df_aliquots[df_aliquots['status'] == 'Checked Out'])
        stored_df = df_aliquots[df_aliquots['status'] == 'Stored']
        type_counts = stored_df['specimen_type'].value_counts().to_dict()
        
    return {
        'total_boxes': total_boxes,
        'active_boxes': active_boxes,
        'empty_boxes': total_boxes - active_boxes,
        'total_aliquots_stored': total_stored,
        'total_aliquots_checked_out': total_checked_out,
        'type_counts_stored': type_counts
    }

def get_recent_aliquots(limit=50):
    df = get_sheet_data("aliquots")
    if df.empty:
        return pd.DataFrame()
    df['id'] = pd.to_numeric(df['id'])
    df = df.sort_values(by='id', ascending=False).head(limit)
    
    # Calculate days since stored dynamically
    now = datetime.now()
    if 'stored_time' in df.columns:
        df['days_since_stored'] = pd.to_datetime(df['stored_time'], errors='coerce').apply(lambda x: (now - x).days if pd.notnull(x) else 0)
        
    cols = [c for c in ['location_id', 'patientvisit_id', 'specimen_type', 'status', 'sent_to', 'stored_time', 'days_since_stored', 'checkout_time', 'checkin_user_id', 'checkout_user_id'] if c in df.columns]
    return df[cols]

def get_all_aliquots_df():
    df = get_sheet_data("aliquots")
    if df.empty:
        return pd.DataFrame()
    
    df['id'] = pd.to_numeric(df['id'])
    df = df.sort_values(by='id', ascending=True)
    
    now = datetime.now()
    if 'stored_time' in df.columns:
        df['days_since_stored'] = pd.to_datetime(df['stored_time'], errors='coerce').apply(lambda x: (now - x).days if pd.notnull(x) else 0)
    
    cols = [c for c in ['location_id', 'patientvisit_id', 'specimen_type', 'status', 'sent_to', 'stored_time', 'days_since_stored', 'checkout_time', 'checkin_user_id', 'checkout_user_id'] if c in df.columns]
    res = df[cols].copy()
    
    # rename for display
    rename_map = {
        "location_id": "Location ID",
        "patientvisit_id": "Patient-Visit ID",
        "specimen_type": "Specimen Type",
        "status": "Status",
        "sent_to": "Sent To",
        "stored_time": "Stored Time",
        "days_since_stored": "Days Stored",
        "checkout_time": "Checkout Time",
        "checkin_user_id": "Check-in User",
        "checkout_user_id": "Check-out User"
    }
    res.rename(columns=rename_map, inplace=True)
    return res

def upload_aliquots_data(df_up):
    # This Google Sheets version of upload simply reads the entire aliquots sheet, merges in pandas, and pushes back
    required = ["Location ID", "Patient-Visit ID", "Specimen Type", "Status"]
    for col in required:
        if col not in df_up.columns:
            return False, f"Missing required column: {col}"
            
    df_aliquots = get_sheet_data("aliquots")
    if df_aliquots.empty:
        df_aliquots = pd.DataFrame(columns=[
            "id", "location_id", "box_id", "x_coord", "y_coord", 
            "patientvisit_id", "specimen_type", "status",
            "sent_to", "stored_time", "days_since_stored",
            "checkout_time", "checkin_user_id", "checkout_user_id"
        ])
    
    df_boxes = get_sheet_data("boxes")
    df_boxes['id'] = pd.to_numeric(df_boxes['id'])
    
    updates = 0
    inserts = 0
    
    next_id = 1
    if not df_aliquots.empty:
        df_aliquots['id'] = pd.to_numeric(df_aliquots['id'])
        next_id = int(df_aliquots['id'].max()) + 1
        
    for idx, row in df_up.iterrows():
        loc_id = str(row["Location ID"]).strip()
        pv_id = str(row["Patient-Visit ID"]).strip()
        s_type = str(row["Specimen Type"]).strip()
        status = str(row["Status"]).strip()
        
        m = re.match(r"D(\d+)R(\d+)L(\d+)B(\d+)X(\d+)Y(\d+)", loc_id)
        if not m:
            continue
        d, r, l, b, x, y = [int(v) for v in m.groups()]
        
        box_match = df_boxes[
            (df_boxes['door_num'] == str(d)) | (df_boxes['door_num'] == d) & 
            (df_boxes['rack_num'] == str(r)) | (df_boxes['rack_num'] == r) &
            (df_boxes['level_num'] == str(l)) | (df_boxes['level_num'] == l) &
            (df_boxes['box_num'] == str(b)) | (df_boxes['box_num'] == b)
        ]
        
        if box_match.empty:
            continue
            
        box_id = int(box_match.iloc[0]['id'])
        
        existing_idx = df_aliquots[df_aliquots['location_id'] == loc_id].index
        
        if not existing_idx.empty:
            df_aliquots.loc[existing_idx, ['patientvisit_id', 'specimen_type', 'status', 'box_id', 'x_coord', 'y_coord']] = \
                [pv_id, s_type, status, box_id, x, y]
            updates += 1
        else:
            new_row = pd.DataFrame([{
                "id": next_id,
                "location_id": loc_id,
                "box_id": box_id,
                "x_coord": x,
                "y_coord": y,
                "patientvisit_id": pv_id,
                "specimen_type": s_type,
                "status": status,
                "sent_to": "",
                "stored_time": "",
                "days_since_stored": 0,
                "checkout_time": "",
                "checkin_user_id": "",
                "checkout_user_id": ""
            }])
            df_aliquots = pd.concat([df_aliquots, new_row], ignore_index=True)
            next_id += 1
            inserts += 1

    write_sheet_data("aliquots", df_aliquots)
    
    # Recalculate boxes
    # This would usually be heavy on GSheets, but we only do this once on upload
    for b_idx, b_row in df_boxes.iterrows():
        b_id = b_row['id']
        b_aliq = df_aliquots[df_aliquots['box_id'] == b_id]
        if not b_aliq.empty:
            count = len(b_aliq)
            # Find most common type or max type
            sp_type = b_aliq['specimen_type'].max()
            df_boxes.loc[b_idx, 'spots_used'] = count
            df_boxes.loc[b_idx, 'specimen_type'] = sp_type
        else:
            df_boxes.loc[b_idx, 'spots_used'] = 0
            df_boxes.loc[b_idx, 'specimen_type'] = ""
            
    write_sheet_data("boxes", df_boxes)
    
    return True, f"Successfully processed spreadsheet! Inserted: {inserts}, Updated: {updates}"
