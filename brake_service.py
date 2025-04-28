import logging
import time
from openobd import *

# Logging setup
logging.basicConfig(level=logging.INFO)
log_file_path = "brake_service_exit_log.txt"

def log_response(data):
    with open(log_file_path, "a") as log_file:
        log_file.write(data + "\n")

def send_request(adb, command, expected_prefix):
    try:
        response = adb.request(uds_command=command, silent=True)
        logging.info(f"Raw Response: {response}")
        log_response(f"{command} => {response}")
        if response.startswith(expected_prefix):
            return response[len(expected_prefix):]
        else:
            logging.warning(f"Unexpected response for {command}: {response}")
            return None
    except ResponseException as e:
        logging.error(f"Request failed: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None

def perform_brake_service_exit(adb):
    print("\n--- Brake Service Mode Exit ---")
    print("⚠️ Make sure the following conditions are met:")
    print("- All repairs completed")
    print("- Vehicle lifted")
    print("- Hood open")
    print("- Ignition ON")
    print("- Parking brake released\n")
    input("Press ENTER to continue...")

    print("🔧 Entering extended diagnostic session...")
    send_request(adb, "1003", "50")
    time.sleep(0.5)

    print("🔧 Starting routine: Move pistons forward...")
    start_response = send_request(adb, "310103A0", "71")
    if start_response:
        print("✅ Routine Start accepted.")
    else:
        print("⚠️ Routine Start failed or not acknowledged.")
        return

    time.sleep(1)

    print("🔧 Finishing routine: Confirm piston movement...")
    stop_response = send_request(adb, "310203A0", "71")
    if stop_response:
        print("✅ Routine Stop accepted. Brake service mode exited.")
    else:
        print("⚠️ Routine Stop failed. Check vehicle conditions.")

def run_brake_exit(ticket_id):
    print("\nStarting session...")
    obd = OpenOBD()
    session = obd.start_session_on_ticket(ticket_id)
    SessionTokenHandler(session)

    # CAN Bus setup (adjust if needed for other vehicles)
    bus = BusConfiguration(
        bus_name="brake_bus",
        can_bus=CanBus(
            pin_plus=6,
            pin_min=14,
            can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
            can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
            transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH
        )
    )
    StreamHandler(session.configure_bus).send_and_close([bus])

    # Channel to relevant brake ECU (example request/response ID, adjust if needed)
    brake_channel = IsotpChannel(
        bus_name="brake_bus",
        request_id=0x737,
        response_id=0x77D,
        padding=Padding.PADDING_ENABLED
    )
    brake_ecu = IsotpSocket(session, brake_channel)

    perform_brake_service_exit(brake_ecu)

    brake_ecu.stop_stream()
    session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
    print("\n✅ Session completed successfully.")

if __name__ == "__main__":
    print("=== Brake Service Mode Exit ===")
    ticket_id = input("Enter Ticket ID: ")
    if not ticket_id.isdigit():
        print("\033[91mInvalid ticket ID. Must be numeric.\033[0m")
    else:
        run_brake_exit(ticket_id)
