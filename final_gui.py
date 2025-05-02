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
from PIL import Image

# Logging setup
logging.basicConfig(level=logging.INFO)
logging.info("Author: yayra.osias@lkqbelgium.be")
logging.info("VAG Information Retrieval")

google_credentials_str = os.getenv("GOOGLE_DRIVE_CREDENTIALS")

if not google_credentials_str:
    print("❌ ERROR: Missing Google Drive Credentials! Set 'GOOGLE_DRIVE_CREDENTIALS' in Replit Secrets.")
    exit(1)

GOOGLE_CREDENTIALS = json.loads(google_credentials_str)



#########################################################
# Load Google Drive credentials
#credentials_str = st.secrets["GOOGLE_DRIVE_CREDENTIALS"]
#if not credentials_str:
    #st.error("❌ Missing Google Drive Credentials!")
    #st.stop()
#GOOGLE_CREDENTIALS = json.loads(credentials_str)
#######################################################



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
        if data:
            vin = next((item["VIN"] for item in data if "VIN" in item), "N/A")
            st.session_state["last_vin"] = vin
            st.session_state["last_modules"] = [entry.get("Module", "") for entry in data]
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
    existing_df.fillna("", inplace=True)

    # Normalize types to strings
    existing_df["VAG Part Number"] = existing_df["VAG Part Number"].astype(str)
    existing_df["Available Versions"] = existing_df["Available Versions"].astype(str)

    to_add = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for entry in comparison_data:
        part_no = str(entry["VAG Part Number"])
        versions = entry.get("Available Versions", "")
        version_list = [v.strip() for v in versions.split(",") if v.strip().isdigit()]

        for version in version_list:
            match = existing_df[
                (existing_df["VAG Part Number"] == part_no) &
                (existing_df["Available Versions"] == version)
            ]
            if match.empty:
                to_add.append({
                    "VAG Part Number": part_no,
                    "Available Versions": version,
                    "Timestamp": timestamp
                })

    if to_add:
        st.info("➕ Updating Sheet3 with new entries...")
        updated_df = pd.concat([existing_df, pd.DataFrame(to_add)], ignore_index=True)
        set_with_dataframe(sheet3, updated_df)
        st.success("✅ Sheet3 updated.")
    else:
        st.info("✅ Sheet3 already contains all entries. No update needed.")



##############################################################

# Define modules
all_modules = {
    "01_ECM": {"request_id": 0x07E0, "response_id": 0x07E8}, # 0x0710, 0x077A (new models golf 8)
    "51_E_Drivetrain": {"request_id": 0x17FC007C, "response_id":0x17FE007C, "skip_1003": True},
    "03_ABS_ESP": {"request_id": 0x0713, "response_id": 0x077D},
    "C6_EV_OBC": {"request_id": 0x0744, "response_id": 0x07AE},
    "23_BKV": {"request_id": 0x073B, "response_id": 0x07A5},
    "16_Steering Wheel": {"request_id": 0x070C, "response_id": 0x0776},
    "15_SRS_Airbag": {"request_id": 0x0715, "response_id": 0x077F},
    "23_EBKV": {"request_id": 0x073B, "response_id": 0x07A5},
    "75_SOS-MODULE": {"request_id": 0x0767, "response_id": 0x07D1},
    "44_EPS": {"request_id": 0x0712, "response_id": 0x077C},
    "AC_SCR": {"request_id": 0x0794, "response_id": 0x072A},
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

# Decode response helper
def decode_utf8(response):
    if response and response.startswith("62"):
        try:
            return binascii.unhexlify(response[6:]).decode("utf-8").strip()
        except Exception:
            return "N/A"
    return "No response"

def get_valid_response(socket, command, tries=2, timeout=5):
    responses = socket.request_multiple(command, tries=tries, timeout=timeout)
    for r in responses:
        if r and r.startswith("62"):
            return r
    return None


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
                rows = sheet3_db[sheet3_db["VAG Part Number"] == part_number]
                if rows.empty:
                    return []

                # Ensure we're working with a clean Series
                versions_series = pd.Series(rows["Available Versions"])
                versions_clean = versions_series.dropna().astype(str).unique().tolist()

                try:
                    # Sort versions numerically if possible
                    return sorted(versions_clean, key=lambda x: int(x))
                except ValueError:
                    # Fall back to alphanumeric sort
                    return sorted(versions_clean)



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
                    if not module_info.get("skip_1003"):
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

                        if available_versions:
                            
                            # Cast versions to integers only if they are digit strings
                            numeric_versions = [int(v) for v in available_versions if v.isdigit()]
                            current_version_int = int(sw_ver) if sw_ver.isdigit() else None

                            if numeric_versions and current_version_int is not None:
                                highest_version = max(numeric_versions)
                                is_newer = current_version_int > highest_version
                                is_older = current_version_int < highest_version
                                highest_version_display = str(highest_version)
                            else:
                                highest_version = "N/A"
                                is_newer = False
                                is_older = False
                                highest_version_display = "N/A"

                            comparison_entry = {
                                "VAG Part Number": part_no,
                                "Current Version": sw_ver,
                                "Available Versions": ", ".join(available_versions),
                                "Highest Known Version": highest_version_display,
                                "Note": "⚠️ Vehicle version is newer!" if is_newer else "",

                            }

                            info_msg = (
                                f"📢 {part_no} | Current: {sw_ver} | "
                                f"Available: {', '.join(available_versions)} | "
                                f"Highest: {highest_version_display}"
                            )

                            if is_newer:
                                info_msg += " 🔺 Vehicle version is newer than Sheet3!"
                            elif is_older:
                                info_msg += f" ✅ ECU can be updated to version {highest_version_display}"

                            st.info(info_msg)

                        else:
                            comparison_entry = {
                                "VAG Part Number": part_no,
                                "Current Version": sw_ver,
                                "Available Versions": ", ".join(available_versions),
                                "Highest Known Version": highest_version_display,
                                "Note": (
                                    "⚠️ Vehicle version is newer!" if is_newer else
                                    f"✅ Update available: {highest_version_display}" if is_older else ""
                                )
                            }

                            st.warning(f"📢 {part_no} | Current: {sw_ver} | No known versions in Sheet3.")

                        version_data.append(comparison_entry)

                    module_socket.stop_stream()

                except Exception as e:
                    st.error(f"❌ Error during communication with {module_name}: {e}")

            if raw_data:
                save_data_to_google_sheets(raw_data, "VAG_data", "Sheet1")
            if version_data:
                save_data_to_google_sheets(version_data, "VAG_data", "Sheet2")
                update_sheet3_if_needed("VAG_data", "Sheet3", version_data)
                st.session_state["last_versions"] = version_data


            openobd_session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
            st.success("✅ Module info request completed.")

        except Exception as e:
            st.error(f"❌ Failed to complete scan: {e}")




def export_scan_to_pdf():
    raw = st.session_state.get("last_scan_raw", [])
    if not raw:
        st.warning("No scan data available yet.")
        return

    df = pd.DataFrame(raw)

    # Include version comparison if available
    if "last_versions" in st.session_state:
        version_df = pd.DataFrame(st.session_state["last_versions"])
        if not version_df.empty:
            df = pd.merge(df, version_df, on="VAG Part Number", how="left")

    pdf_buffer = io.BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis('off')

        # Optional logo
        logo_path = "logo2.png"
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            ax.imshow(img, aspect='auto', extent=[0, 1, 0.9, 1.1], zorder=-1, alpha=0.6)

        # Header
        header = f"Scan Report\nVIN: {st.session_state.get('last_vin', 'N/A')}\nModules: {', '.join(st.session_state.get('last_modules', []))}"
        ax.text(0.5, 1.02, header, ha='center', fontsize=10, transform=ax.transAxes)

        # Clean columns
        display_columns = [col for col in df.columns if col not in ["Timestamp"]]
        display_df = df[display_columns]

        table = ax.table(cellText=display_df.values, colLabels=display_df.columns, loc='center')
        table.scale(1, 1.5)
        pdf.savefig(fig)
        plt.close()

    st.download_button(
        label="📥 Download PDF",
        data=pdf_buffer.getvalue(),
        file_name=f"vag_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/pdf"
    )


# PDF Export toggle
if st.checkbox("📄 Export last scan to PDF (if available)"):
    def export_scan_to_pdf():
        raw = st.session_state.get("last_scan_raw", [])
        if not raw:
            st.warning("No scan data available yet.")
            return

        df = pd.DataFrame(raw)

        # Merge with version comparison if available
        if "last_versions" in st.session_state:
            version_df = pd.DataFrame(st.session_state["last_versions"])
            if not version_df.empty:
                df = pd.merge(df, version_df, on="VAG Part Number", how="left")

        pdf_buffer = io.BytesIO()
        with PdfPages(pdf_buffer) as pdf:
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.axis('off')

            # Optional logo
            logo_path = "logo2.png"
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                ax.imshow(img, aspect='auto', extent=[0, 1, 0.9, 1.1], zorder=-1, alpha=0.6)

            header = f"Scan Report\nVIN: {st.session_state.get('last_vin', 'N/A')}\nModules: {', '.join(st.session_state.get('last_modules', []))}"
            ax.text(0.5, 1.02, header, ha='center', fontsize=10, transform=ax.transAxes)

            display_columns = [col for col in df.columns if col not in ["Timestamp"]]
            display_df = df[display_columns]

            table = ax.table(cellText=display_df.values, colLabels=display_df.columns, loc='center')
            table.scale(1, 1.5)
            pdf.savefig(fig)
            plt.close()

        st.download_button(
            label="📥 Download PDF",
            data=pdf_buffer.getvalue(),
            file_name=f"vag_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf"
        )

    # Run export
    export_scan_to_pdf()

# Exit session management
with st.expander("🚪 Exit Session OpenOBD (if stuck...)"):
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
