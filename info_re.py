from openobd import *

openobd = OpenOBD()
openobd_session = openobd.start_session_on_ticket("8072735")

SessionTokenHandler(openobd_session)

print("Configuring buses...")
bus_configs = [
    (BusConfiguration(bus_name="bus_6_14",
                     can_bus=CanBus(pin_plus=6, pin_min=14, can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                                    can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                                    transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH))),
    (BusConfiguration(bus_name="bus_3_11",
                     can_bus=CanBus(pin_plus=3, pin_min=11, can_protocol=CanProtocol.CAN_PROTOCOL_ISOTP,
                                    can_bit_rate=CanBitRate.CAN_BIT_RATE_500,
                                    transceiver=TransceiverSpeed.TRANSCEIVER_SPEED_HIGH)))
]

bus_config_stream = StreamHandler(openobd_session.configure_bus)
bus_config_stream.send_and_close(bus_configs)
print("Buses have been configured.")

# Add the new request ID and response ID
adb_channel = IsotpChannel(bus_name="bus_6_14",
       request_id=0x7E6,
       response_id=0x7EE,
       padding=Padding.PADDING_ENABLED)
# Start a stream to communicate with the engine
adb = IsotpSocket(openobd_session, adb_channel)

# extended diagnostic session
print("Sending 1003...")
response = adb.request("1003", silent=True)
print(f"Response: {response}")

try:


    print("Sending 22F190 for VIN...")
    response = adb.request("22F190", tries=2, timeout=5)
    print(f"Response: {response}")

    # Decode VIN, ignoring the first 3 bytes
    vin = bytes.fromhex(response[6:]).decode("utf-8") if response else ""
    print(f"VIN: {vin}")

    print("Sending 22F187 for Factory part Number...")
    response = adb.request("22F187", tries=2, timeout=5)
    print(f"Response: {response}")

    #decode FActory number with UTF 8
    factory_number = bytes.fromhex(response[6:]).decode("utf-8") if response else ""
    print(f"Factory Number: {factory_number}")

    print("Sending 22F191 for Hardware Number...")
    response = adb.request("22F191", tries=2, timeout=5)
    print(f"Response: {response}")

    #decode Hardware number with UTF 8
    hardware_number = bytes.fromhex(response[6:]).decode("utf-8") if response else ""
    print(f"Hardware Number: {hardware_number}")

    print("Sending 22F18A for Supplier Number...")
    response = adb.request("22F18A", tries=2, timeout=5)
    print(f"Response: {response}")

    #decode Supplier number with UTF 8
    supplie_number = bytes.fromhex(response[6:]).decode("utf-8") if response else ""
    print(f"Supplier Number: {supplie_number}")

    print("Sending 22F195 for SW Version...")
    response = adb.request("22F195", tries=2, timeout=5)
    print(f"Response: {response}")

    #decode SW Version with UTF 8
    sw_version = bytes.fromhex(response[6:]).decode("utf-8") if response else ""
    print(f"SW Version: {sw_version}")


except ResponseException as e:
    print(f"Request failed: {e}")

finally:
    # Close the stream regardless of the result
    adb.stop_stream()

# Close the session with a successful result
result = ServiceResult(result=[Result.RESULT_SUCCESS])
openobd_session.finish(result)