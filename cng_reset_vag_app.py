import logging
import streamlit as st
from openobd import *
from datetime import datetime
import pytz
import os

# Logging configuration
logging.basicConfig(level=logging.INFO)
log_folder = "logs"
os.makedirs(log_folder, exist_ok=True)
log_file_path = os.path.join(log_folder, "cng_reset_log.txt")

def log_response(data):
    with open(log_file_path, "a") as log_file:
        log_file.write(data + "\n")

def save_session_data(ticket_id, vin, ecu_name, pre_days, post_days, status):
    timestamp = datetime.now(pytz.timezone("Europe/Brussels")).strftime("%Y-%m-%d %H:%M:%S")
    save_path = os.path.join(log_folder, f"cng_reset_session_log.csv")
    header = "timestamp,ticket_id,vin,ecu,pre_days,post_days,status\n"
    line = f"{timestamp},{ticket_id},{vin},{ecu_name},{pre_days},{post_days},{status}\n"
    if not os.path.exists(save_path):
        with open(save_path, "w") as f:
            f.write(header)
    with open(save_path, "a") as f:
        f.write(line)

def send_request(cng, command, expected_prefix):
    try:
        response = cng.request(command, silent=True)
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

def perform_cng_reset(ticket_id):
    session = None
    sockets = []

    try:
        logging.info("Starting session...")
        obd = OpenOBD()
        session = obd.start_session_on_ticket(ticket_id)
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

        ecus = [
            {"name": "CNG", "req_id": 0x0714, "res_id": 0x077E, "reset": True},
            {"name": "ECM", "req_id": 0x07E0, "res_id": 0x07E8, "reset": False},
            {"name": "Gateway", "req_id": 0x0710, "res_id": 0x077A, "reset": True}
        ]

        for ecu in ecus:
            st.markdown(f"### Communicating with {ecu['name']} ECU")
            cng = IsotpSocket(session, IsotpChannel(
                bus_name="vag_bus",
                request_id=ecu["req_id"],
                response_id=ecu["res_id"],
                padding=Padding.PADDING_ENABLED))
            sockets.append(cng)

            vin = ""
            try:
                ecu_info = send_request(cng, "22F19E", "62F19E")
                sw_version = send_request(cng, "22F1A2", "62F1A2")
                vin_id = send_request(cng, "22F190", "62F190")
                vin = decode_utf8(vin_id or "")

                st.write("ECU Info:", decode_utf8(ecu_info or ""))
                st.write("SW Version:", decode_utf8(sw_version or ""))
                st.write("VIN:", vin)
            except Exception as e:
                logging.warning(f"Could not read data from {ecu['name']}: {e}")

            send_request(cng, "1003", "50")

            if ecu["reset"]:
                send_request(cng, "2EF1988000000E5D23", "6EF198")
                send_request(cng, "2EF199250409", "6EF199")

                pre_reset = send_request(cng, "220C38", "620C38")
                pre_days = decode_service_counter(pre_reset)
                st.write(f"{ecu['name']} pre-reset counter: {pre_days} days")

                send_request(cng, "2E0C3401", "6E0C34")

                post_reset = send_request(cng, "220C38", "620C38")
                post_days = decode_service_counter(post_reset)
                st.write(f"{ecu['name']} post-reset counter: {post_days} days")

                status = "Success" if post_days is not None and pre_days is not None and post_days < pre_days else "Failed"
                save_session_data(ticket_id, vin, ecu["name"], pre_days, post_days, status)

                if status == "Success":
                    st.success(f"✅ Reset successful for {ecu['name']} ECU!")
                else:
                    st.error(f"❌ Reset failed or counter unchanged on {ecu['name']} ECU.")

    except Exception as e:
        logging.error(f"Error: {e}")
        st.error(f"Unexpected error: {e}")
        return False
    finally:
        if session:
            session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
        for sock in sockets:
            sock.stop_stream()

st.title("🚘 VAG CNG Service Reset Tool")
ticket_id = st.text_input("Enter Ticket ID")
if st.button("Start Reset"):
    if ticket_id.isdigit():
        perform_cng_reset(ticket_id)
    else:
        st.error("Ticket ID must be numeric.")

log_download = os.path.join(log_folder, "cng_reset_session_log.csv")
if os.path.exists(log_download):
    with open(log_download, "rb") as file:
        st.download_button("Download Session Log", file, file_name="cng_reset_session_log.csv")
