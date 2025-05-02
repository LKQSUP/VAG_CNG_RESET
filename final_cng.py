import logging
import streamlit as st
from openobd import *
import pandas as pd
from datetime import datetime
import pytz
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Logging configuration
logging.basicConfig(level=logging.INFO)
log_file_path = "cng_reset_log.txt"
session_csv_path = "cng_reset_sessions.csv"
SPREADSHEET_ID = "1uazxFUibJQsQ_VVmCzN-Z4lbc6zvzI2UQDCLNVf05XQ"
SHEET_NAME = "cng_data"

# Expected column order for Google Sheet
EXPECTED_COLUMNS = [
    "timestamp", "ticket_id", "CNG_pre_days", "CNG_post_days",
    "Gateway_pre_days", "Gateway_post_days", "vin", "brand_guess",
    "reset_period_years"#, "Kolom 1"
]

# Initialize OpenOBD
openobd = OpenOBD()

def upload_csv_with_service_account(file_path, file_name='cng_reset_sessions.csv', folder_id=None):
    try:
        creds_str = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
        if not creds_str:
            logging.error("Missing Google Drive Credentials!")
            return

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(creds_str),
            scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=credentials)

        media = MediaFileUpload(file_path, mimetype='text/csv')
        response = service.files().list(q=f"name='{file_name}' and trashed=false", fields="files(id, name)").execute()
        st.success("✅ Data appended to Google Sheet.")

        files = response.get('files', [])

        if files:
            file_id = files[0]['id']
            file = service.files().update(fileId=file_id, media_body=media, fields='id').execute()
            logging.info(f"✅ Updated: https://drive.google.com/file/d/{file['id']}/view")
        else:
            metadata = {'name': file_name}
            if folder_id:
                metadata['parents'] = [folder_id]
            file = service.files().create(body=metadata, media_body=media, fields='id').execute()
            logging.info(f"✅ Uploaded: https://drive.google.com/file/d/{file['id']}/view")
    except Exception as e:
        logging.error(f"❌ Drive upload failed: {e}")

    st.info(f"✅ CSV uploaded to Google Drive.")


def append_to_google_sheet(data_dict, spreadsheet_id, sheet_name):
    try:
        creds_str = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
        if not creds_str:
            logging.error("Missing Google Drive Credentials!")
            return

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(creds_str),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()

        for col in EXPECTED_COLUMNS:
            if col not in data_dict:
                data_dict[col] = ""

        values = [[data_dict[col] for col in EXPECTED_COLUMNS]]

        result = sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values}
        ).execute()

        st.success("✅ Data appended to Google Sheet.")
        #st.info(f"Append result: {result}") # to debug and show if it succesfull added 
        st.info(f"Data Successfully added to file: {sheet_name}")

        logging.info("✅ Data appended to Google Sheet.")
    except Exception as e:
        st.error(f"❌ Google Sheets API error: {e}")

        logging.error(f"❌ Failed to write to Google Sheet: {e}")

def log_response(data):
    with open(log_file_path, "a") as log_file:
        log_file.write(data + "\n")

def send_request(gas, command, expected_prefix):
    try:
        response = gas.request(command, silent=True)
        logging.info(f"Raw Response: {response}")
        if response.startswith(expected_prefix):
            return response[len(expected_prefix):]
        else:
            logging.warning(f"Unexpected response format for {command}")
            return None
    except ResponseException as e:
        logging.error(f"Request failed: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None

def decode_utf8(hex_string):
    try:
        return bytes.fromhex(hex_string).decode("utf-8").strip("\x00")
    except:
        return ""

def decode_service_counter(hex_response):
    try:
        return int(hex_response[-4:], 16)
    except:
        return None

def guess_vag_brand(vin):
    if not vin or len(vin) < 3:
        return "Unknown"
    wmi = vin[:3].upper()
    return {
        "WVW": "Volkswagen", "WV1": "Volkswagen Commercial",
        "WAU": "Audi", "TRU": "Audi (Hungary)",
        "SKZ": "Skoda", "TMB": "Skoda",
        "VSS": "SEAT", "3VW": "Volkswagen (Mexico)",
        "9BW": "Volkswagen (Brazil)"
    }.get(wmi, "Unknown")




def perform_cng_reset(ticket_id, reset_years):
    session = None
    sockets = []
    try:
        session = openobd.start_session_on_ticket(ticket_id)
        SessionTokenHandler(session)

        bus = BusConfiguration(
            bus_name="vag_bus",
            can_bus=CanBus(
                pin_plus=6,
                pin_min=14,
                can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH
            )
        )
        StreamHandler(session.configure_bus).send_and_close([bus])

        cng_ecu = {"name": "CNG", "req_id": 0x0714, "res_id": 0x077E}
        now = datetime.now(pytz.timezone("Europe/Brussels"))
        session_data = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "ticket_id": ticket_id,
            "reset_period_years": reset_years
        }

        st.markdown(f"### Communicating with {cng_ecu['name']} ECU")
        gas = IsotpSocket(session, IsotpChannel(
            bus_name="vag_bus",
            request_id=cng_ecu["req_id"],
            response_id=cng_ecu["res_id"],
            padding=Padding.PADDING_ENABLED))
        sockets.append(gas)

        ecu_info = send_request(gas, "22F19E", "62F19E")
        sw_version = send_request(gas, "22F1A2", "62F1A2")
        vin_id = send_request(gas, "22F190", "62F190")
        decoded_vin = decode_utf8(vin_id or "")
        session_data["vin"] = decoded_vin
        session_data["brand_guess"] = guess_vag_brand(decoded_vin)

        st.write("VIN:", decoded_vin)
        st.write("Brand (guessed):", session_data["brand_guess"])
        st.write("ECU Info:", decode_utf8(ecu_info or ""))
        st.write("SW Version:", decode_utf8(sw_version or ""))

        send_request(gas, "1003", "50")
        send_request(gas, "2EF1988000000E5D23", "6EF198")
        send_request(gas, "2EF199250409", "6EF199")

        pre_reset = send_request(gas, "220C38", "620C38")
        pre_days = decode_service_counter(pre_reset)
        st.write(f"{cng_ecu['name']} pre-reset counter: {pre_days} days")

        if reset_years == 4:
            send_request(gas, "2E0C3405B4", "6E0C34")
        else:
            send_request(gas, "2E0C3402DA", "6E0C34")

        post_reset = send_request(gas, "220C38", "620C38")
        post_days = decode_service_counter(post_reset)
        st.write(f"{cng_ecu['name']} post-reset counter: {post_days} days")

        log_response(f"{cng_ecu['name']} Pre-reset CNG counter: {pre_days}")
        log_response(f"{cng_ecu['name']} Post-reset CNG counter: {post_days}")

        session_data["CNG_pre_days"] = pre_days
        session_data["CNG_post_days"] = post_days

        if post_days is not None and pre_days is not None:
            st.success(f"✅ Reset command successfully sent to {cng_ecu['name']} ECU!")
            st.info("🔔 Reminder: Drive the car or perform ignition cycle 1 min off & on.")
        else:
            st.error(f"❌ Reset failed: unable to read counter after reset on {cng_ecu['name']} ECU.")

        st.write("Session data going to sheet:", session_data)


        for col in EXPECTED_COLUMNS:
            if col not in session_data:
                session_data[col] = ""

        df = pd.DataFrame([session_data])
        try:
            existing_df = pd.read_csv(session_csv_path)
            df = pd.concat([existing_df, df], ignore_index=True)
        except FileNotFoundError:
            pass
        df.to_csv(session_csv_path, index=False)

        upload_csv_with_service_account(session_csv_path)
        append_to_google_sheet(session_data, SPREADSHEET_ID, SHEET_NAME)

    except Exception as e:
        logging.error(f"Error: {e}")
        st.error(f"Unexpected error: {e}")
    finally:
        try:
            if session:
                session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
        except Exception as e:
            logging.error(f"Error finishing session: {e}")
        try:
            for sock in sockets:
                sock.stop_stream()
        except Exception as e:
            logging.error(f"Error closing socket: {e}")

# --- Streamlit UI ---
st.warning("⚠️ This page is being updated. Some features may reload or behave differently during updates.", icon="⚠️")
st.info("📢 A new update is coming soon! If you experience issues, please contact **LKQ Support: Yayra.osias@lkqbelgium.be**", icon="ℹ️")



st.title("\U0001F698 VAG CNG Service Reset")
ticket_id = st.text_input("Enter Ticket ID")
reset_years = st.selectbox("Select Reset Period", options=[2, 4], format_func=lambda x: f"{x} years")

if st.button("Start Reset"):
    if ticket_id.isdigit():
        perform_cng_reset(ticket_id, reset_years)
    else:
        st.error("Ticket ID must be numeric.")

if st.button("Check Active Sessions"):
    session_list_object = openobd.get_session_list()
    if not session_list_object.sessions:
        st.info("No sessions currently active.")
    else:
        st.warning("Active sessions found:")
        for session_info in session_list_object.sessions:
            st.write(f"State: {session_info.state}, Created at: {session_info.created_at}")
        terminate = st.selectbox("Select session to terminate:", [f"{s.id}" for s in session_list_object.sessions])
        if st.button("Terminate Selected Session"):
            openobd.interrupt_session(session_id=SessionId(value=terminate))
            st.success(f"Session {terminate} has been interrupted.")

if st.button("Show Saved Sessions"):
    try:
        df = pd.read_csv(session_csv_path)
        st.dataframe(df)
        st.download_button(
            label="\U0001F4C5 Download Session Log",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name="cng_reset_sessions.csv",
            mime="text/csv"
        )
    except FileNotFoundError:
        st.info("No saved session data found.")
