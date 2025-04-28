import streamlit as st
from openobd import *
from fpdf import FPDF
import time
import requests
from functools import lru_cache
import os

# --- Replit Secrets ---
RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]
RAPIDAPI_HOST = os.environ["RAPIDAPI_HOST"]

@lru_cache(maxsize=256)
def translate_dtc_online(dtc_code):
    url = f"https://{RAPIDAPI_HOST}/dtc/{dtc_code}"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("description", "Unknown DTC")
        else:
            return f"No info (status {response.status_code})"
    except Exception as e:
        return f"API error: {e}"

def decode_dtc_response(hex_data):
    dtcs = []
    try:
        hex_data = hex_data[4:]  # Remove 5902 or service ID prefix
        while len(hex_data) >= 6:
            raw_dtc = hex_data[:6]
            hex_data = hex_data[6:]
            dtc_type = raw_dtc[0]
            code_type = {"0": "P", "1": "C", "2": "B", "3": "U"}.get(dtc_type, "P")
            dtc = code_type + raw_dtc[1:]
            dtcs.append(dtc)
    except Exception as e:
        dtcs.append(f"Error decoding DTCs: {e}")
    return dtcs

def run_prescan(ticket_number):
    logs = []
    dtc_list = []
    try:
        openobd = OpenOBD()
        session = openobd.start_session_on_ticket(ticket_number)
        SessionTokenHandler(session)
        logs.append("OpenOBD session started.")

        logs.append("Configuring buses...")
        bus_configs = [
            BusConfiguration(bus_name="bus_6_14",
                             can_bus=CanBus(pin_plus=6, pin_min=14, can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                                            can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                                            transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH)),
            BusConfiguration(bus_name="bus_3_11",
                             can_bus=CanBus(pin_plus=3, pin_min=11, can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                                            can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                                            transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH))
        ]
        bus_config_stream = StreamHandler(session.configure_bus)
        bus_config_stream.send_and_close(bus_configs)
        logs.append("Buses configured successfully.")

        ecm_channel = IsotpChannel(bus_name="bus_6_14", request_id=0x7E6, response_id=0x7EE, padding=Padding.PADDING_ENABLED)
        ecm = IsotpSocket(session, ecm_channel)

        logs.append("Sending 1003 (Extended Diagnostic Session)...")
        response = ecm.request("1003", silent=True)
        logs.append(f"1003 Response: {response}")

        logs.append("Sending 22F190 (VIN request)...")
        response = ecm.request("22F190", tries=2, timeout=5)
        logs.append(f"22F190 Response: {response}")
        vin = bytes.fromhex(response[6:]).decode("utf-8") if response else "Unknown"
        logs.append(f"VIN: {vin}")

        logs.append("Reading DTCs with 1902...")
        dtc_response = ecm.request("1902", tries=2, timeout=5)
        logs.append(f"Raw DTC Response: {dtc_response}")

        dtcs = decode_dtc_response(dtc_response)
        for dtc in dtcs:
            if dtc.startswith("Error"):
                dtc_list.append(dtc)
                logs.append(dtc)
            else:
                desc = translate_dtc_online(dtc)
                dtc_list.append(f"{dtc} - {desc}")
                logs.append(f"DTC: {dtc} - {desc}")

        ecm.stop_stream()
        session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
        logs.append("OpenOBD session finished.")
        return vin, dtc_list, logs

    except ResponseException as e:
        logs.append(f"Request failed: {e}")
        return "ERROR", dtc_list, logs
    except Exception as e:
        logs.append(f"Unexpected error: {e}")
        return "ERROR", dtc_list, logs

def generate_pdf(ticket_number, vin, dtcs, logs):
    filename = f"pre_scan_report_{ticket_number}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt=f"Pre-Scan Report - Ticket #{ticket_number}", ln=True)
    pdf.cell(200, 10, txt=f"Scan Time: {time.ctime()}", ln=True)
    pdf.cell(200, 10, txt=f"VIN: {vin}", ln=True)
    pdf.ln(10)

    if dtcs:
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt="Detected DTCs:", ln=True)
        pdf.set_font("Arial", size=10)
        for dtc in dtcs:
            pdf.cell(200, 10, txt=dtc, ln=True)
    else:
        pdf.cell(200, 10, txt="No DTCs found.", ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 10, txt="Logs:", ln=True)
    pdf.set_font("Arial", size=10)
    for log in logs:
        pdf.multi_cell(0, 10, log)
    pdf.output(filename)
    return filename

# --- Streamlit UI ---
st.set_page_config(page_title="Remote Pre-Scan Tool", page_icon="🔧")
st.title("🔧 Remote Vehicle Pre-Scan Tool")

ticket = st.text_input("Enter Ticket Number")

if st.button("Run Pre-Scan") and ticket:
    with st.spinner("Scanning..."):
        vin, dtcs, log_entries = run_prescan(ticket)
        report_file = generate_pdf(ticket, vin, dtcs, log_entries)
    st.success("Pre-scan completed!")
    st.download_button("Download PDF Report", open(report_file, "rb"), file_name=report_file)

    if dtcs:
        st.subheader("❗ Detected DTCs")
        for dtc in dtcs:
            st.write(f"- {dtc}")
            if "API error" in dtc or "No info" in dtc:
                st.error(f"⚠️ Issue translating DTC: {dtc}")
    else:
        st.success("No DTCs found!")

    with st.expander("📄 Scan Log"):
        for entry in log_entries:
            st.text(entry)
