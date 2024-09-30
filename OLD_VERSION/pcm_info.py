import logging

logging.basicConfig(level=logging.INFO)
logging.info("Author: OSIAS")
logging.info("YAYRA.OSIAS@LKQBEGIUM.BE")

from openobd import *

# Start an openOBD session on a ticket
openobd = OpenOBD()
openobd_session = openobd.start_session_on_ticket("8059499")
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

try:

    print("Sending request for VIN...")
    response = ecm.request("22F190", tries=2, timeout=5)
    if response:
        VIN = bytes.fromhex(response[6:]).decode("utf-8")
        print(f"VIN: {VIN}")
    else:
        print("Request failed")

    #Request FActory part Number=======================================

    print("Sending request for Factory part Number...")
    response = ecm.request("22F187", tries=2, timeout=5)
    if response:
        print("Request OK")
        factory_number = bytes.fromhex(response[6:]).decode("utf-8")
        print(f"Factory Number: {factory_number}")
    else:
        print("Request failed")

    #Request for Hardware number====================================

    print("Sending request for Hardware Number...")
    response = ecm.request("22F191", tries=2, timeout=5)
    if response:
        print("Request OK")
        HW_number = bytes.fromhex(response[6:]).decode("utf-8")
        print(f"Hardware Number: {HW_number}")
    else:
        print("Request failed")

    #Supplier number request========================================

    print("Sending request for Supplier Number...")
    response = ecm.request("22F18A", tries=2, timeout=5)
    if response:
        print("Request OK")
        # Decode Supplier Number, ignoring the first 3 bytes
        supplier_number = bytes.fromhex(response[6:]).decode("utf-8")
        print(f"Supplier Number: {supplier_number}")
    else:
        print("Request failed: SupplierNot available")

#SW_versie request=================================================

    print("Sending request for SW Version...")
    response = ecm.request("22F195", tries=2, timeout=5)

    if response:
        print("Request OK")
        sw_version = bytes.fromhex(response[6:]).decode("utf-8")

        print(f"SW Version: {sw_version}")
    else:
        print("Request failed")

    #SW_number request===============================================

    print("Sending request for SW_Number...")
    response = ecm.request("22F194", tries=2, timeout=5)

    if response:
        print("Request OK")
        sw_number = bytes.fromhex(response[6:]).decode("utf-8")

        print(f"SW Number: {sw_number}")
    else:
        print("Request failed")
    """
    print("Sending 2203 for Mileage...")
    response = ecm.request("2203", tries=2, timeout=5)
    print(f"Response: {response}")

    # Decode mileage as a hexadecimal string to an integer (dec)
    mileage_hex = response[6:] if response else "000000"  
    mileage_int = int(mileage_hex, 16)  # Convert to integer
    print(f"Mileage: {mileage_int}")






    print("Sending 22F18C for SW Versionr...")
    response = ecm.request("22F18", tries=2, timeout=5)
    print(f"Response: {response}")

    #decodsw version  SW version with UTF 8
    SW_version = bytes.fromhex(
        response[6:]).decode("utf-8") if response else ""
    print(f"Supplier Number: {SW_version}")


    print("Sending 22F195 for supplier number...")
    response = ecm.request("22F195", tries=2, timeout=5)
    print(f"Response: {response}")

    #decode SW Version with UTF 8
    supplie_number = bytes.fromhex(
        response[6:]).decode("utf-8") if response else ""
    print(f"SW Version: {supplie_number}")

   """

except ResponseException as e:
    print(f"Request failed: {e}")

finally:

    ecm.stop_stream()

    # Close the stream regardless of the result

# Close the session with a successful result
result = ServiceResult(result=[Result.RESULT_SUCCESS])
openobd_session.finish(result)
