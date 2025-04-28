import binascii
import json
import logging
import os
import io
import gspread
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime
from pytz import timezone
from matplotlib.backends.backend_pdf import PdfPages
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials
from openobd import *

# Logging setup
logging.basicConfig(level=logging.INFO)
logging.info("Author: yayra.osias@lkqbelgium.be")
logging.info("VAG Information Retrieval")



google_credentials_str = os.getenv("GOOGLE_DRIVE_CREDENTIALS")

if not google_credentials_str:
    print("❌ ERROR: Missing Google Drive Credentials! Set 'GOOGLE_DRIVE_CREDENTIALS' in Replit Secrets.")
    exit(1)

GOOGLE_CREDENTIALS = json.loads(google_credentials_str)





# Load Google Drive credentials
#credentials_str = st.secrets["GOOGLE_DRIVE_CREDENTIALS"]
#if not credentials_str:
    #st.error("❌ Missing Google Drive Credentials!")
   # st.stop()
#GOOGLE_CREDENTIALS = json.loads(credentials_str)




# Authenticate Google Drive
def authenticate_google_drive():
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS, scopes)
    return gspread.authorize(credentials)

# Get worksheet
def get_google_sheet(sheet_name, worksheet_name):
    try:
        client = authenticate_google_drive()
        sheet = client.open(sheet_name).worksheet(worksheet_name)
        return sheet
    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"⚠ Worksheet '{worksheet_name}' not found. Creating it...")
        sheet = client.open(sheet_name).add_worksheet(title=worksheet_name, rows="1000", cols="20")
        return sheet
    except Exception as e:
        st.error(f"❌ ERROR accessing Google Sheets: {e}")
        st.stop()

# Save data to Google Sheets
def save_data_to_google_sheets(data, sheet_name, worksheet_name):
    try:
        if not data:
            return
        timestamp = datetime.now(timezone("Europe/Brussels")).strftime("%Y-%m-%d %H:%M:%S")
        for entry in data:
            entry["Timestamp"] = timestamp
        df_new = pd.DataFrame(data)
        df_new.fillna("N/A", inplace=True)
        sheet = get_google_sheet(sheet_name, worksheet_name)
        existing_data = get_as_dataframe(sheet, evaluate_formulas=True, header=0)
        existing_data.dropna(how="all", inplace=True)
        combined_data = pd.concat([existing_data, df_new], ignore_index=True)
        set_with_dataframe(sheet, combined_data)
        st.success(f"✅ Data saved to {worksheet_name}")
        st.session_state["last_scan_raw"] = data
    except Exception as e:
        st.error(f"❌ ERROR saving data to {worksheet_name}: {e}")

# Load Sheet3 database
def load_sheet3_db(sheet_name, worksheet_name):
    try:
        sheet = get_google_sheet(sheet_name, worksheet_name)
        db = pd.DataFrame(sheet.get_all_records())
        db.fillna("", inplace=True)
        return db
    except Exception as e:
        st.error(f"❌ ERROR loading Sheet3 database: {e}")
        return pd.DataFrame()

# Update Sheet3 dynamically if needed
def update_sheet3_if_needed(sheet_name, worksheet_name, comparison_data):
    sheet3 = get_google_sheet(sheet_name, worksheet_name)
    existing_df = pd.DataFrame(sheet3.get_all_records())
    to_add = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for entry in comparison_data:
        part_no = entry["VAG Part Number"]
        available_versions = entry["Available Versions"]
        match = existing_df[(existing_df["VAG Part Number"] == part_no) & (existing_df["Available Versions"] == available_versions)]
        if match.empty:
            entry["Timestamp"] = timestamp
            to_add.append(entry)
    if to_add:
        st.info("➕ Updating Sheet3 with new entries...")
        updated_df = pd.concat([existing_df, pd.DataFrame(to_add)], ignore_index=True)
        set_with_dataframe(sheet3, updated_df)
        st.success("✅ Sheet3 updated.")
    else:
        st.info("✅ Sheet3 already contains all entries. No update needed.")

#####################################################################

# Define modules
all_modules = {
    "01_ECM": {"request_id": 0x07E0, "response_id": 0x07E8},
    "C6_EV_OBC": {"request_id": 0x0744, "response_id": 0x07AE},
    "23_BKV": {"request_id": 0x073B, "response_id": 0x07A5},

    "15_SRS_Airbag": {"request_id": 0x0715, "response_id": 0x077F},
    "23_EBKV": {"request_id": 0x073B, "response_id": 0x07A5},
    "75_SOS-MODULE": {"request_id": 0x0767, "response_id": 0x07D1},
    "44_EPS": {"request_id": 0x0712, "response_id": 0x077C},
    #"8C_BECM": {"request_id": 0x07ED, "response_id": 0x07E5},
    "55_AFS_LIGHT": {"request_id": 0x0754, "response_id": 0x07BE},
    "02_TCM": {"request_id": 0x07E1, "response_id": 0x07E9},
    "17_IPC": {"request_id": 0x0714, "response_id": 0x077E},
    "19_GTW": {"request_id": 0x0710, "response_id": 0x077A},
    "09_BCM": {"request_id": 0x070E, "response_id": 0x0778},
    "15_SRS": {"request_id": 0x0715, "response_id": 0x077F},
    "13_ACC": {"request_id": 0x0757, "response_id": 0x07C1},
    "A5_FRONTSENSORS": {"request_id": 0x074F, "response_id": 0x07B9},
}

st.title("🚗 VAG Module Scanner")
st.write("Scan VAG vehicle modules and log data to the cloud.")

ticket_id = st.text_input("Enter Remote Ticket ID", "", max_chars=20)

if ticket_id and ticket_id.isdigit():
    scan_mode = st.radio("Select Scan Mode:", ["Full Scan", "Scan by Module"])
    selected_modules = {}

    if scan_mode == "Full Scan":
        selected_modules = all_modules
    elif scan_mode == "Scan by Module":
        selected_keys = st.multiselect("Choose modules to scan:", options=list(all_modules.keys()))
        selected_modules = {k: all_modules[k] for k in selected_keys}

    if st.button("Run Scan"):
        try:
            st.write("Starting OpenOBD Session...")
            openobd = OpenOBD()
            openobd_session = openobd.start_session_on_ticket(ticket_id)
            SessionTokenHandler(openobd_session)

            bus_config = BusConfiguration(
                bus_name="VAG_bus",
                can_bus=CanBus(
                    pin_plus=6,
                    pin_min=14,
                    can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                    can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                    transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH,
                ),
            )
            StreamHandler(openobd_session.configure_bus).send_and_close([bus_config])
            st.success("✅ CAN bus configured.")

            sheet3_db = load_sheet3_db("VAG_data", "Sheet3")

            def decode_utf8(response):
                if response and not response.startswith("7F"):
                    try:
                        return binascii.unhexlify(response[6:]).decode("utf-8").strip()
                    except Exception:
                        return "N/A"
                return "No response"

            def check_sheet3_versions(part_number):
                row = sheet3_db[sheet3_db["VAG Part Number"] == part_number]
                if not row.empty:
                    return row["Available Versions"].values[0]
                return "N/A"

            raw_data = []
            version_data = []

            for module_name, module_info in selected_modules.items():
                st.write(f"\n===== Scanning {module_name} =====")
                try:
                    channel = IsotpChannel(
                        bus_name="VAG_bus",
                        request_id=module_info["request_id"],
                        response_id=module_info["response_id"],
                        padding=Padding.PADDING_ENABLED,
                    )
                    module_socket = IsotpSocket(openobd_session, channel)
                    module_socket.request("1003", tries=2, timeout=5)

                    module_entry = {"Module": module_name}
                    part_no = ""
                    sw_ver = ""

                    for label, cmd in {"VIN": "22F190", "VAG Part Number": "22F187", "Software Version": "22F189"}.items():
                        response = module_socket.request(cmd, tries=2, timeout=5)
                        decoded = decode_utf8(response)
                        module_entry[label] = decoded
                        if label == "VAG Part Number":
                            part_no = decoded
                        if label == "Software Version":
                            sw_ver = decoded

                    raw_data.append(module_entry)

                    if part_no and sw_ver:
                        available_versions = check_sheet3_versions(part_no)
                        comparison_entry = {
                            "VAG Part Number": part_no,
                            "Current Version": sw_ver,
                            "Available Versions": available_versions,
                        }
                        version_data.append(comparison_entry)
                        st.info(f"📢 {part_no} | Current: {sw_ver} | Available: {available_versions}")

                    module_socket.stop_stream()

                except Exception as e:
                    st.error(f"❌ Error during communication with {module_name}: {e}")

            if raw_data:
                save_data_to_google_sheets(raw_data, "VAG_data", "Sheet1")
            if version_data:
                save_data_to_google_sheets(version_data, "VAG_data", "Sheet2")
                update_sheet3_if_needed("VAG_data", "Sheet3", version_data)

            openobd_session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
            st.success("✅ Module info request completed.")

        except Exception as e:
            st.error(f"❌ Failed to complete scan: {e}")



#############################################################




# PDF Export Section
def export_scan_to_pdf():
    raw = st.session_state.get("last_scan_raw", [])
    if not raw:
        st.warning("No scan data available yet.")
        return

    df = pd.DataFrame(raw)
    pdf_buffer = io.BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis('off')
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center')
        table.scale(1, 2)
        pdf.savefig(fig)
        plt.close()

    st.download_button(
        label="📥 Download PDF",
        data=pdf_buffer.getvalue(),
        file_name="vag_scan_results.pdf",
        mime="application/pdf"
    )


# Dummy scan button

#if st.button("Simulate Scan"):
   # example_data = [{"Module": "01_ECM", "VAG Part Number": "03L906023", "Software Version": "0010"}]
   # save_data_to_google_sheets(example_data, "VAG_data", "Sheet1")
   # st.success("Scan complete!")



# PDF Export toggle
if st.checkbox("📄 Export last scan to PDF (if available)"):
    export_scan_to_pdf()

# Graceful Exit
with st.expander("🚪 Exit Safely"):
    openobd = OpenOBD()
    session_list = openobd.get_session_list()

    if not session_list.sessions:
        st.success("✅ No active OpenOBD sessions.")
    else:
        st.warning("⚠️ Active OpenOBD sessions detected:")
        session_display = [
            f"{i + 1}. ID: {s.id} | State: {s.state} | Created: {s.created_at}"
            for i, s in enumerate(session_list.sessions)
        ]
        selected_display = st.multiselect("Select session(s) to close:", options=session_display)

        if selected_display:
            for display in selected_display:
                try:
                    idx = int(display.split(".")[0]) - 1
                    sid = session_list.sessions[idx].id
                    openobd.interrupt_session(session_id=SessionId(value=sid))
                    st.success(f"✅ Session {sid} closed.")
                except Exception as e:
                    st.error(f"❌ Failed to close session: {e}")

    if st.button("Logout and Exit"):
        st.success("👋 Logged out. Application will now exit.")
        st.stop()
