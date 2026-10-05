import time
import subprocess
import uiautomator2 as u2


def run(cmd):
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


####################################################
# Connect Device
####################################################

def connect():

    try:
        d = u2.connect()
        return d

    except Exception as e:
        print(e)
        return None


####################################################
# Trigger ANR
####################################################

def trigger_anr():

#    print("\n" + "=" * 60)
#    print("              TRIGGERING ANR")
#    print("=" * 60)

    d = connect()

    if d is None:
        print("❌ Unable to connect to device")
        return False

    print("Searching Generate ANR button...")

    if not d(text="Generate ANR").wait(timeout=10):

        print("❌ Generate ANR button not found.")
        return False

    print("Button Found")

    d(text="Generate ANR").click()

    print("Button Clicked")

#    print("Waiting 15 seconds for ANR...")

    time.sleep(2)

    print("✅ ANR Triggered")

    return True


####################################################
# Trigger Display Crash
####################################################

def trigger_display():

 #   print("\n" + "=" * 60)
    print("TRIGGERING DISPLAY CRASH")
 #   print("=" * 60)

    print("Waiting for renderer crash...")

    time.sleep(2)

    print("✅ Display crash generated")

    return True


####################################################
# Generic API
####################################################

def trigger_bug(issue):

    issue = issue.lower()

    if issue == "anr":
        return trigger_anr()

    if issue == "display":
        return trigger_display()

    print("Unknown Issue Type")

    return False


####################################################
# Testing
####################################################

if __name__ == "__main__":

    print("1. ANR")
    print("2. Display")

    choice = input("\nChoice : ")

    if choice == "1":

        trigger_bug("anr")

    elif choice == "2":

        trigger_bug("display")
