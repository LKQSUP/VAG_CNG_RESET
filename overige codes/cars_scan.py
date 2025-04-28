import logging
import streamlit as st
from openobd import *
import pandas as pd
from datetime import datetime
import pytz
import time

# Setup
logging.basicConfig(level=logging.INFO)
openobd = OpenOBD()

# Commonly used VAG ECU IDs
COMMON_VAG_ECU_IDS = [
    0x01, 0x02, 0x03, 0x08, 0x09, 0x0F,
    0x15, 0x16, 0x17, 0x19, 0x25, 0x29,
    0x42, 0x44, 0x46, 0x47, 0x52, 0x53,
    0x55, 0x56, 0x5F, 0x61, 0x65, 0x6C,
    0x6D, 0x76, 0x77, 0x7D
]

def guess_vag_brand(vin):
    if not vin or len(vin) < 3:
        return "Unknown"
    return {
        "WVW": "Volkswagen", "WV1": "Volkswagen Commercial", "WAU": "Audi",
        "TRU": "Audi (Hungary)", "SKZ": "Skoda", "TMB": "Skoda",
        "VSS": "SEAT", "3VW": "Volkswagen (Mexico)", "9BW": "Volkswagen (Brazil)"
    }.get(vin[:3].upper(), "Unknown")

def decode_utf8(hex_string):
    try:
        return bytes.fromhex(hex_string).decode("utf-8").strip("\x00")
    except Exception:
        return ""

def decode_ecu_function(ecu_info):
    known_ecus = {
        "J104": "ABS/ESP",
        "J519": "Body Control Module (BCM)",
        "J527": "Steering Wheel Module",
        "J500": "Power Steering Control",
        "J393": "Central Locking",
        "J285": "Instrument Cluster",
        "J623": "Engine Control Module (ECM)",
        "J345": "Airbag Control Unit",
        "J533": "Gateway",
        "J743": "Mechatronics DSG",
        "J255": "Climatronic Control",
        "J367": "Battery Regulation",
        "J428": "Adaptive Cruise Control",
        "J941": "Light Control",
    }
    for code, label in known_ecus.items():
        if code in ecu_info:
            return label
    return "Unknown / Not Mapped"

def send_request(gas, command, expected_prefix):
    try:
        response = gas.request(command, silent=True)
        logging.info(f"Response for {command}: {response}")
        if response.startswith(expected_prefix):
            return response[len(expected_prefix):]
    except Exception as e:
        logging.debug(f"Request failed: {e}")
    return None

def fast_ecu_scan(ticket_id):
    session = None
    try:
        st.info("🔌 Starting diagnostic session...")
        session = openobd.start_session_on_ticket(ticket_id)
        SessionTokenHandler(session)

        # Configure CAN bus
        bus = BusConfiguration(
            bus_name="vag_bus",
            can_bus=CanBus(
                pin_plus=6, pin_min=14,
                can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH
            )
        )
        StreamHandler(session.configure_bus).send_and_close([bus])

        st.markdown("## 🔍 Scanning VAG ECUs...")
        detected = []

        for ecu_id in COMMON_VAG_ECU_IDS:
            req_id = 0x700 + ecu_id
            res_id = 0x780 + ecu_id

            try:
                gas = IsotpSocket(session, IsotpChannel(
                    bus_name="vag_bus",
                    request_id=req_id,
                    response_id=res_id,
                    padding=Padding.PADDING_ENABLED,
                    timeout_ms=200
                ))

                # Try extended diagnostic session (1003), fallback to default (1001)
                session_response = send_request(gas, "1003", "50")
                if not session_response:
                    session_response = send_request(gas, "1001", "50")

                if session_response:
                    vin_raw = send_request(gas, "22F190", "62F190")
                    sw_raw = send_request(gas, "22F1A2", "62F1A2")
                    name_raw = send_request(gas, "22F19E", "62F19E")

                    if vin_raw or sw_raw or name_raw:
                        decoded_name = decode_utf8(name_raw or "")
                        ecu_entry = {
                            "ECU ID": hex(ecu_id),
                            "Req ID": hex(req_id),
                            "Res ID": hex(res_id),
                            "VIN": decode_utf8(vin_raw or ""),
                            "SW Version": decode_utf8(sw_raw or ""),
                            "ECU Info": decoded_name,
                            "Function": decode_ecu_function(decoded_name)
                        }
                        detected.append(ecu_entry)
                        st.success(f"✅ ECU found at ID {hex(ecu_id)}")
                        st.write(ecu_entry)


                

                    if vin_raw or sw_raw or name_raw:
                        decoded_name = decode_utf8(name_raw or "")
                        ecu_entry = {
                        "ECU ID": hex(ecu_id),
                        "Req ID": hex(req_id),
                        "Res ID": hex(res_id),
                        "VIN": decode_utf8(vin_raw or ""),
                        "SW Version": decode_utf8(sw_raw or ""),
                        "ECU Info": decoded_name,
                        "Function": decode_ecu_function(decoded_name)
                    }
                    
                        detected.append(ecu_entry)
                        st.success(f"✅ ECU found at ID {hex(ecu_id)}")
                        st.write(ecu_entry)

                gas.stop_stream()
                time.sleep(0.05)  # Prevent CAN flooding
            except Exception as e:
                logging.debug(f"No response from ECU ID {hex(ecu_id)}: {e}")

        if detected:
            vin = detected[0]["VIN"]
            st.markdown("### 🚗 Vehicle Info")
            st.write("VIN:", vin)
            st.write("Brand Guess:", guess_vag_brand(vin))

            df = pd.DataFrame(detected)
            st.dataframe(df)
            st.download_button(
                "📥 Download ECU Report",
                df.to_csv(index=False).encode('utf-8'),
                file_name="fast_vag_ecu_scan.csv",
                mime="text/csv"
            )
        else:
            st.warning("No ECUs responded in this scan.")
    except Exception as e:
        st.error(f"❌ Error during scan: {e}")
    finally:
        if session:
            session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))

# Streamlit UI
st.title("⚡ Fast VAG ECU Scanner with Function Mapping")
ticket_id = st.text_input("Enter Ticket ID")

if st.button("Start ECU Scan"):
    if ticket_id.isdigit():
        fast_ecu_scan(ticket_id)
    else:
        st.error("Ticket ID must be numeric.")
