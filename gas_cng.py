import logging
from openobd import *

# Setup logging
logging.basicConfig(level=logging.INFO)
log_file = "cng_service_reset_log.txt"

def log_response(data):
    with open(log_file, "a") as f:
        f.write(data + "\n")

def send_request(cng, command, expected_prefix):
    try:
        response = cng.request(command, silent=True)
        logging.info(f"Response: {response}")
        if response.startswith(expected_prefix):
            return response[len(expected_prefix):]
        return None
    except ResponseException as e:
        logging.error(f"Request failed: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None

def decode_utf8(hex_str):
    try:
        bytes_data = bytes.fromhex(hex_str)
        return bytes_data.decode('utf-8').strip('\x00')
    except Exception:
        return "[Decode Error]"

def perform_cng_reset(ticket_id):
    cng = None
    session = None

    try:
        openobd = OpenOBD()
        session = openobd.start_session_on_ticket(ticket_id)
        SessionTokenHandler(session)

        # Configure CAN2 bus
        can_config = [
            BusConfiguration(
                bus_name="can_vag",
                can_bus=CanBus(pin_plus=6, pin_min=14,
                               can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                               can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                               transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH)
            )
        ]
        StreamHandler(session.configure_bus).send_and_close(can_config)
        logging.info("CAN bus configured.")

        # Set up communication channel
        channel = IsotpChannel(bus_name="can_vag",
                               request_id=0x0714,
                               response_id=0x077E,
                               padding=Padding.PADDING_ENABLED)
        cng = IsotpSocket(session, channel)

        # Step 1: Request VIN and Software Version
        vin_hex = send_request(cng, "22F19E", "62F19E")
        sw_hex = send_request(cng, "22F1A2", "62F1A2")
        vin = decode_utf8(vin_hex) if vin_hex else "Unknown"
        sw = decode_utf8(sw_hex) if sw_hex else "Unknown"
        logging.info(f"VIN: {vin}")
        logging.info(f"Software Version: {sw}")
        log_response(f"VIN: {vin}")
        log_response(f"Software Version: {sw}")

        # Step 2: Enter Extended Session
        diag_resp = send_request(cng, "1003", "50")
        if diag_resp is None:
            logging.error("Extended session failed.")
            return False

        # Step 3: Send initial reset commands
        send_request(cng, "2EF1988000000E5D23", "6EF198")
        send_request(cng, "2EF199250409", "6EF199")

        # Step 4: Read service data before reset
        initial_service = send_request(cng, "220C38", "620C38")
        log_response(f"Initial Service Counter: {initial_service}")

        # Step 5: Send the actual reset command
        reset_resp = send_request(cng, "2E0C3401", "6E0C34")
        if reset_resp is None:
            logging.error("Reset command failed.")
            return False

        # Step 6: Confirm reset
        confirm_service = send_request(cng, "220C38", "620C38")
        log_response(f"Post-reset Service Counter: {confirm_service}")

        print("\033[92mCNG Service Reset successfully performed!\033[0m")
        return True

    except Exception as e:
        logging.error(f"Unhandled error: {e}")
        print(f"\033[91mUnexpected error: {e}\033[0m")
        return False
    finally:
        if session:
            session.finish(ServiceResult(result=[Result.RESULT_SUCCESS]))
        if cng:
            cng.stop_stream()

# Entry point
if __name__ == "__main__":
    print("=== VAG CNG Service Reset Tool ===")
    ticket = input("Enter OpenOBD Ticket ID: ").strip()
    if not ticket.isdigit():
        print("\033[91mInvalid Ticket ID. Must be numeric.\033[0m")
    else:
        print("\nStarting reset process...\n")
        success = perform_cng_reset(ticket)
        print("\n=== RESULT ===")
        if success:
            print("\033[92mCNG Reset Completed Successfully.\033[0m")
        else:
            print("\033[91mCNG Reset Failed.\033[0m")
