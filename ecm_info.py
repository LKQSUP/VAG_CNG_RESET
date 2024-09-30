import logging
from openobd import *

logging.basicConfig(level=logging.INFO)
logging.info("Author: OSIAS")
logging.info("YAYRA.OSIAS@LKQBEGIUM.BE")


# Start an openOBD session (replace with your credentials)
openobd = OpenOBD()
openobd_session = openobd.start_session_on_ticket("8066797")
SessionTokenHandler(openobd_session)

# Define two buses with the ISO-TP protocol
print("Configuring buses...")
bus_configs = [
    (BusConfiguration(
        bus_name="bus_6_14",
        can_bus=CanBus(pin_plus=6,
                       pin_min=14,
                       can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                       can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                       transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH))),
    (BusConfiguration(
        bus_name="bus_3_11",
        can_bus=CanBus(pin_plus=3,
                       pin_min=11,
                       can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                       can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                       transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH)))
]
# Open a configureBus stream, send the bus configurations, and close the stream
bus_config_stream = StreamHandler(openobd_session.configure_bus)
bus_config_stream.send_and_close(bus_configs)
print("Buses have been configured.")

# Define an ISO-TP channel for the ECU_motor

ecm_channel = IsotpChannel(bus_name="bus_6_14",
                           request_id=0x7E0,
                           response_id=0x7E8,
                           padding=Padding.PADDING_ENABLED)
# Start a stream to communicate with the engine
ecm = IsotpSocket(openobd_session, ecm_channel)

print("Sending 1003...")
response = ecm.request("1003", silent=True)
print(f"Response: {response}")

# Loop through all requests
requests = {
    "VIN": "22F190",
    "Engine code": "22F1AD",
    "Factory Part Number": "22F187",
    "Hardware Number": "22F191",
    "Motor Type + part number": "22F19E",
    "Supplier Number": "22F18A",
    "SW Version": "22F189",
    #"SW Number": "22F194",
    #"Mileage": "2203",
    # "SW Versionr": "22F18C",
}

for name, command in requests.items():
    print(f"Sending request for {name}...")
    try:
        response = ecm.request(command, tries=2, timeout=5)
        if response:
            print("Request OK")
            # Decode the response as a hexadecimal string
            response_hex = response[6:]
            # Try decoding to UTF-8, handle potential errors
            try:
                data = bytes.fromhex(response_hex).decode("utf-8")
                print(f"{name}: {data}")
            except UnicodeDecodeError:
                # If decoding fails, print the raw hexadecimal data
                print(f"{name}: (Could not decode to UTF-8) {response_hex}")
        else:
            print("Request failed")

    except Exception as e:
        logging.error(f"Request failed: {e}")