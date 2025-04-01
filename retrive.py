from openobd import *


# Retrieve all current openOBD sessions
openobd = OpenOBD()
session_list_object = openobd.get_session_list()

# Check if any sessions were returned
if len(session_list_object.sessions) == 0:
    print("No sessions currently active.")
else:
    # Print some info on each SessionInfo object that was returned
    print("Current sessions:")
    for number, session_info in enumerate(session_list_object.sessions, 1):
        session_info_string = f"State: {session_info.state}, created at: {session_info.created_at}."
        print(f"{number}. {session_info_string}")

    while True:
        try:
            # Continue asking which session should be interrupted until a valid input has been given
            choice = int(input("Which session do you want to interrupt? Enter 0 to cancel.\n"))
            if choice == 0:
                print("No sessions were interrupted.")
            else:
                # A session has been selected, so interrupt it
                selected_session = session_list_object.sessions[choice - 1]
                openobd.interrupt_session(session_id=SessionId(value=selected_session.id))
                print(f"Session with ID {selected_session.id} has been interrupted.")
            break

        except (ValueError, IndexError):
            print("Invalid input. Please enter a valid number")
        except OpenOBDException as e:
            print(e)

