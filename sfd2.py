########### Checkif vehicule is with SFD2 or not #########################



import logging
from openobd import *

logging.basicConfig(level=logging.INFO)
logging.info("Author: OSIAS")
logging.info("YAYRA.OSIAS@LKQBEGIUM.BE")


# Start an openOBD session (replace with your credentials)
openobd = OpenOBD()
openobd_session = openobd.start_session_on_ticket("8072918")
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

gtw_channel = IsotpChannel(bus_name="bus_6_14",
                           request_id=0x710,
                           response_id=0x77A,
                           padding=Padding.PADDING_ENABLED)
# Start a stream to communicate with the engine
gtw = IsotpSocket(openobd_session, gtw_channel)

print("Sending 1003...")
response = gtw.request("1003", silent=True)
print(f"Response: {response}")

# Loop through all requests
requests = {
    "VIN": "22F190",
    "Factory Part Number": "22F187",
    "unknow": "22F1A2",
    "ECU Type": "22F19E",
    #"Supplier Number": "22F18A",
    "SW Version": "22F189",
    #"SW Number": "22F194",
    #"Mileage": "2203",
    # "SW Versionr": "22F18C",
 
    # ECU Type: EV_GatewICAS1MEBUNECE
}

#if reponse of the request ECU Type is EV_GatewICAS1MEBUNECE than it is SFD2


for name, command in requests.items():
    print(f"Sending request for {name}...")
    try:
        response = gtw.request(command, tries=2, timeout=5)
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