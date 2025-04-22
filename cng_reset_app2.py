import logging
import streamlit as st
from openobd import *
import pandas as pd
from datetime import datetime
import pytz

# Logging configuration
logging.basicConfig(level=logging.INFO)
log_file_path = "cng_reset_log.txt"
session_csv_path = "cng_reset_sessions.csv"

# Initialize OpenOBD object
openobd = OpenOBD()

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
    except Exception:
        return ""

def decode_service_counter(hex_response):
    try:
        return int(hex_response[-4:], 16)
    except:
        return None


# Helper function to guess the brand based on VIN
def guess_vag_brand(vin):
    if not vin or len(vin) < 3:
        return "Unknown"

    wmi = vin[:3].upper()

    vag_brands = {
        "WVW": "Volkswagen",
        "WV1": "Volkswagen Commercial",
        "WAU": "Audi",
        "TRU": "Audi (Hungary)",
        "SKZ": "Skoda", 
        "TMB": "Skoda",
        "VSS": "SEAT",
        "3VW": "Volkswagen (Mexico)",
        "9BW": "Volkswagen (Brazil)",
    }

    return vag_brands.get(wmi, "Unknown")



# start ticket----------------------------------------------------------

def perform_cng_reset(ticket_id):
    session = None
    sockets = []
    report = []

    try:
        logging.info("Starting session...")
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
        logging.info("Bus configured.")

        cng_ecu = {"name": "CNG", "req_id": 0x0714, "res_id": 0x077E, "reset": True}
        now = datetime.now(pytz.timezone("Europe/Brussels"))
        session_data = {"timestamp": now.strftime("%Y-%m-%d %H:%M:%S"), "ticket_id": ticket_id}

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
        st.write("VIN:", decoded_vin)
        session_data["vin"] = decoded_vin
        session_data["brand_guess"] = guess_vag_brand(decoded_vin)
        st.write("Brand (guessed):", session_data["brand_guess"])


        #vin_id = send_request(gas, "22F190", "62F190")

        st.write("ECU Info:", decode_utf8(ecu_info or ""))
        st.write("SW Version:", decode_utf8(sw_version or ""))
        #st.write("VIN:", decode_utf8(vin_id or ""))

        send_request(gas, "1003", "50")

        send_request(gas, "2EF1988000000E5D23", "6EF198")
        send_request(gas, "2EF199250409", "6EF199")

        pre_reset = send_request(gas, "220C38", "620C38")
        pre_days = decode_service_counter(pre_reset)
        st.write(f"{cng_ecu['name']} pre-reset counter: {pre_days} days")

        send_request(gas, "2E0C3401", "6E0C34")

        post_reset = send_request(gas, "220C38", "620C38")
        post_days = decode_service_counter(post_reset)
        st.write(f"{cng_ecu['name']} post-reset counter: {post_days} days")

        log_response(f"{cng_ecu['name']} Pre-reset CNG counter: {pre_days}")
        log_response(f"{cng_ecu['name']} Post-reset CNG counter: {post_days}")

        session_data[f"{cng_ecu['name']}_pre_days"] = pre_days
        session_data[f"{cng_ecu['name']}_post_days"] = post_days

        if post_days is not None and pre_days is not None and post_days < pre_days:
            st.success(f"✅ Reset successful for {cng_ecu['name']} ECU!")
        else:
            st.error(f"❌ Reset failed or counter unchanged on {cng_ecu['name']} ECU.")

        df = pd.DataFrame([session_data])
        try:
            existing_df = pd.read_csv(session_csv_path)
            df = pd.concat([existing_df, df], ignore_index=True)
        except FileNotFoundError:
            pass
        df.to_csv(session_csv_path, index=False)

    except Exception as e:
        logging.error(f"Error: {e}")
        st.error(f"Unexpected error: {e}")
        return False
    finally:
        if session:
            session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
        for sock in sockets:
            sock.stop_stream()

st.title("🚘 VAG CNG Service Reset ")
ticket_id = st.text_input("Enter Ticket ID")

if st.button("Start Reset"):
    if ticket_id.isdigit():
        perform_cng_reset(ticket_id)
    else:
        st.error("Ticket ID must be numeric.")

if st.button("Check Active Sessions"):
    session_list_object = openobd.get_session_list()
    if len(session_list_object.sessions) == 0:
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
            label="📥 Download Session Log",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name="cng_reset_sessions.csv",
            mime="text/csv"
        )
    except FileNotFoundError:
        st.info("No saved session data found.")
