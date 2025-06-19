import logging
import streamlit as st
from openobd import *
import pandas as pd
from datetime import datetime
import pytz
import os

# === Setup ===
logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="VAG CNG Reset Tool", layout="wide")
st.title("🚗 VAG CNG Reset & Diagnostic Tool")

# === Constants ===
RESET_OPTIONS = {
    "Volkswagen / Audi / Seat / Skoda (Normal)": 4,
    "SKODA option2": 4,
    "Read & Clear DTCs": None
}
SKODA_CMD = "2E0C380E90"
SKODA_RESP = "6E0C38"
session_csv_path = "cng_reset_sessions.csv"
openobd = OpenOBD()

# === Helpers ===
def send_request(sock, command, expected_prefix):
    try:
        response = sock.request(command, silent=True)
        logging.info(f"Raw Response: {response}")
        if response.startswith(expected_prefix):
            return response[len(expected_prefix):]
        else:
            logging.warning(f"Unexpected response format for {command}")
            return None
    except Exception as e:
        logging.error(f"Request failed: {e}")
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

def decode_dtc_bytes(dtc_data):
    dtcs = []
    dtc_bytes = dtc_data[6:]
    for i in range(0, len(dtc_bytes), 6):
        if i + 6 <= len(dtc_bytes):
            raw = dtc_bytes[i:i+6]
            b1 = int(raw[0:2], 16)
            b2 = raw[2:4]
            b3 = raw[4:6]
            type_code = (b1 & 0xC0) >> 6
            type_char = ["P", "C", "B", "U"][type_code]
            dtc = f"{type_char}{(b1 & 0x3F):02X}{b2}{b3}"
            dtcs.append(dtc)
    return dtcs

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

def perform_cng_reset(ticket_id, reset_option):
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

        sock = IsotpSocket(session, IsotpChannel(
            bus_name="vag_bus",
            request_id=0x7E0,
            response_id=0x7E8,
            padding=Padding.PADDING_ENABLED
        ))

        vin_hex = send_request(sock, "22F190", "62F190")
        vin = decode_utf8(vin_hex) if vin_hex else "Unknown"

        cng_pre = send_request(sock, "22F18C", "62F18C")
        gateway_pre = send_request(sock, "22F187", "62F187")

        send_request(sock, "1003", "50")

        if "SKODA" in reset_option.upper():
            reset_cmd = SKODA_CMD
            reset_resp = SKODA_RESP
        else:
            reset_cmd = "2E0C380E8C000000"
            reset_resp = "6E0C38"

        reset_result = send_request(sock, reset_cmd, reset_resp)

        cng_post = send_request(sock, "22F18C", "62F18C")
        gateway_post = send_request(sock, "22F187", "62F187")

        brand = guess_vag_brand(vin)
        now = datetime.now(pytz.timezone("Europe/Brussels")).strftime("%Y-%m-%d %H:%M:%S")

        row = {
            "timestamp": now,
            "ticket_id": ticket_id,
            "CNG_pre_days": decode_service_counter(cng_pre),
            "CNG_post_days": decode_service_counter(cng_post),
            "Gateway_pre_days": decode_service_counter(gateway_pre),
            "Gateway_post_days": decode_service_counter(gateway_post),
            "vin": vin,
            "brand_guess": brand,
            "reset_period_years": RESET_OPTIONS[reset_option],
            "Kolom 1": ""
        }

        df = pd.DataFrame([row])
        df.to_csv(session_csv_path, index=False, mode='a', header=not os.path.exists(session_csv_path))
        st.success("✅ Reset completed and logged.")
        st.json(row)

        sock.stop_stream()
        session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
    except Exception as e:
        logging.error(f"Reset Error: {e}")
        st.error(f"❌ Reset failed: {e}")


##########################################################


tabs = st.tabs(["🔄 Reset", "🛠️ DTC Tool", "📜 History","📟 IPC Reset"])

# === TAB 1: RESET ===
with tabs[0]:
    st.subheader("🔄 Perform CNG Reset")
    ticket_id = st.text_input("Enter Ticket ID", key="reset_ticket")
    reset_option = st.selectbox("Select Function", options=[k for k in RESET_OPTIONS if RESET_OPTIONS[k] is not None])
    if st.button("Start Reset"):
        if not ticket_id.isdigit():
            st.error("Ticket ID must be numeric.")
        else:
            perform_cng_reset(ticket_id, reset_option)

# === TAB 2: DTC TOOL ===
with tabs[1]:
    st.subheader("🛠️ Read & Clear DTCs")
    ticket_id_dtc = st.text_input("Enter Ticket ID", key="dtc_ticket")

    if st.button("Start DTC Session"):
        if not ticket_id_dtc.isdigit():
            st.error("Ticket ID must be numeric.")
        else:
            session = None
            dtc_socket = None
            try:
                session = openobd.start_session_on_ticket(ticket_id_dtc)
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

                fallback_ids = [(0x07E0, 0x07E8), (0x17FC0076, 0x17FE0076)]

                for req_id, res_id in fallback_ids:
                    try:
                        test_socket = IsotpSocket(session, IsotpChannel(
                            bus_name="vag_bus",
                            request_id=req_id,
                            response_id=res_id,
                            padding=Padding.PADDING_ENABLED
                        ))
                        vin_resp = send_request(test_socket, "22F190", "62F190")
                        if vin_resp:
                            dtc_socket = test_socket
                            vin = decode_utf8(vin_resp)
                            break
                        else:
                            test_socket.stop_stream()
                    except Exception as e:
                        logging.warning(f"ECM fallback ID failed: {e}")

                if not dtc_socket:
                    st.error("❌ ECM not responding on any known ID pair.")
                else:
                    st.success("✅ ECM communication established.")

                    partnr = decode_utf8(send_request(dtc_socket, "22F19E", "62F19E") or "")
                    swver = decode_utf8(send_request(dtc_socket, "22F1A2", "62F1A2") or "")

                    st.markdown(f"**VIN:** `{vin}`  \n**Part Number:** `{partnr}`  \n**Software Version:** `{swver}`")

                    send_request(dtc_socket, "1003", "50")

                    raw_dtc = send_request(dtc_socket, "190204", "5902")

                    if not raw_dtc:
                        st.error("❌ No DTC response received.")
                    elif raw_dtc.startswith("FF"):
                        st.success("✅ No DTCs stored.")
                    elif raw_dtc.startswith("FF00"):
                        st.success("✅ No active or stored DTCs.")
                    else:
                        decoded_dtcs = decode_dtc_bytes("5902" + raw_dtc if not raw_dtc.startswith("5902") else raw_dtc)
                        if decoded_dtcs:
                            st.warning("⚠️ DTCs Found:")
                            for dtc in decoded_dtcs:
                                st.markdown(f"- **{dtc}**")
                            if st.button("Clear All DTCs"):
                                clear_response = send_request(dtc_socket, "14FFFFFF", "54")
                                if clear_response:
                                    st.success("✅ DTCs cleared successfully.")
                                else:
                                    st.error("❌ DTC clear command failed.")
                        else:
                            st.success("✅ No valid DTCs decoded.")

                    dtc_socket.stop_stream()

            except Exception as e:
                logging.error(f"DTC Read Error: {e}")
                st.error(f"❌ Unexpected error: {e}")
            finally:
                try:
                    if session:
                        session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
                except Exception as e:
                    logging.error(f"Session close failed: {e}")


# === TAB 3: HISTORY ===
with tabs[2]:
    st.subheader("📜 Previous Reset Logs")
    if os.path.exists(session_csv_path):
        df = pd.read_csv(session_csv_path)
        if not df.empty:
            st.dataframe(df.tail(50).sort_values("timestamp", ascending=False))
        else:
            st.info("🕳️ No reset logs available yet.")
    else:
        st.warning("⚠️ No CSV log file found.")
    if st.button("🔄 Refresh Logs"):
        st.experimental_rerun()




# === TAB 4: RESET IN IPC ====

with tabs[3]:
    st.subheader("📟 Perform IPC (Cluster) Reset – Module 0017")
    ticket_id_ipc = st.text_input("Enter Ticket ID", key="ipc_ticket")

    if st.button("Send IPC Reset"):
        if not ticket_id_ipc.isdigit():
            st.error("Ticket ID must be numeric.")
        else:
            try:
                session = openobd.start_session_on_ticket(ticket_id_ipc)
                SessionTokenHandler(session)

                bus = BusConfiguration(
                    bus_name="ipc_bus",
                    can_bus=CanBus(
                        pin_plus=6,
                        pin_min=14,
                        can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                        can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                        transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH
                    )
                )
                StreamHandler(session.configure_bus).send_and_close([bus])

                ipc_sock = IsotpSocket(session, IsotpChannel(
                    bus_name="ipc_bus",
                    request_id=0x0714,
                    response_id=0x077E,
                    padding=Padding.PADDING_ENABLED
                ))

                st.markdown("🔍 Reading IPC VIN and Part Number...")
                vin_hex = send_request(ipc_sock, "22F190", "62F190")
                vin = decode_utf8(vin_hex) if vin_hex else "Unknown"
                partnr_hex = send_request(ipc_sock, "22F19E", "62F19E")
                partnr = decode_utf8(partnr_hex) if partnr_hex else "Unknown"

                col1, col2 = st.columns(2)
                col1.markdown(f"**VIN:** `{vin}`")
                col2.markdown(f"**Part Number:** `{partnr}`")

                st.markdown("⚙️ Entering Diagnostic Session...")
                diag_result = send_request(ipc_sock, "1003", "50")
                st.success("✅ Extended session OK") if diag_result else st.error("❌ Failed to enter diagnostic session")

                st.markdown("---")
                st.markdown("🔧 Sending IPC reset sequence...")

                def show_cmd_result(cmd, expected_prefix, label):
                    resp = send_request(ipc_sock, cmd, expected_prefix)
                    if resp is not None:
                        st.success(f"✅ {label} acknowledged")
                        return True
                    else:
                        st.error(f"❌ {label} failed")
                        return False

                results = {
                    "F198 Write": show_cmd_result("2EF1988000000CC333", "6EF198", "Write to F198"),
                    "F199 Write": show_cmd_result("2EF199250617", "6EF199", "Write to F199"),
                    "0C34 Write": show_cmd_result("2E0C3401", "6E0C34", "Write to 0C34"),
                    "0C38 Reset": show_cmd_result("2E0C380E91", "6E0C38", "Send final reset")
                }

                if all(results.values()):
                    st.success("🎉 IPC reset sequence completed successfully.")
                else:
                    st.warning("⚠️ Some IPC reset steps failed. Review communication status above.")

                ipc_sock.stop_stream()
                session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))

            except Exception as e:
                logging.error(f"IPC Reset Error: {e}")
                st.error(f"❌ IPC Reset failed: {e}")









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