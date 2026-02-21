# Freezer Inventory Management User Guide

Welcome to the Freezer Inventory Management System! This application helps you accurately store, track, and retrieve Plasma, Serum, and Urine aliquots across a massive 500-box freezer system.

**Access the Live Application Here:** [https://frinvmgt.streamlit.app/](https://frinvmgt.streamlit.app/)

## 1. Getting Started
- **Login:** Access the web application and sign in with your approved credentials. 
- **Navigation:** Use the left sidebar to navigate between your Dashboard, the Storage wizard, the Scan tab, and the Admin Panel.

## 2. Admin Dashboard & Uploads
If you are logged in as a Master Administrator, you have access to two powerful features on the Dashboard:
- **Full Inventory CSV Download:** Instantly download a backup of the entire Google Sheets database locally.
- **Smart Data Uploads:** If you manually tweet the data in Google Sheets (or edit the downloaded CSV locally), you can upload it back into the Streamlit app. The app uses a "Smart Merge" engine: it automatically identifies new aliquots, safely overwrites existing aliquots to match your edits, and comprehensively recalculates the box storage capacities so the math on the dashboard perfectly matches reality.

## 3. Storing New Aliquots
When you receive new samples from a patient visit, use the **Store Aliquots** tab.
1. Enter the unique `Patient-Visit ID` (e.g., `P001-V1`).
2. Input the exact number of Plasma, Serum, and Urine aliquots you want to store (max 10 of each).
3. Click "Allocate Spots & Generate Labels".
4. Click the newly generated blue button to download a PDF of standard `4x1` inch sticker labels you can print and attach directly to the tubes.

### How the Allocation Strategy Works (The 'Brain')
When you click **Allocate Spots**, the system strictly adheres to clinical safety constraints to ensure your freezer remains impeccably organized. It calculates storage spots based on the following rules:

1. **Isolation by Visit:** Aliquots from *different* visits of the *same* patient can never be stored in the same box.
2. **Isolation by Specimen Type:** A single box can only physically hold one type of specimen at a time. Plasma, Serum, and Urine never mix in the same box.
3. **Clustering by Type:** Aliquots of the *same* type, from the *same* visit, for the *same* person are mathematically guaranteed to be clustered inside the exact same box.
4. **Ergonomic Rack Routing (The 3-Pass System):**
   To make physical retrieval as fast as possible for lab techs, the system routes specimens to dedicated racks in a 3-pass search:
   - **Pass 1 (Primary):** Plasma exclusively routes to Rack 1. Serum exclusively routes to Rack 2. Urine exclusively routes to Rack 3.
   - **Pass 2 (Overflow):** If the primary rack is 100% full, the system smoothly falls back and allocates the box to **Rack 4** (the designated overflow safe-zone).
   - **Pass 3 (Emergency):** If Rack 4 is also completely full, the system will frantically secure any empty, valid box anywhere in the freezer to ensure the clinical sample is safely stored.

## 4. Retrieving Aliquots (Scan / Toggle)
When you physically remove an aliquot from the freezer, it must be electronically logged.
1. Navigate to the **Scan / Toggle** tab.
2. Click inside the text box.
3. Use your USB Barcode/QR Scanner to zap the sticker on the aliquot tube.
4. The scanner will automatically input the Location ID (e.g. `D1R1L1B1X1Y1`) and hit enter.
5. The system instantly toggles the item from `Stored` to `Checked Out`! 
   *(Note: Scanning it a second time toggles it back into storage).*
