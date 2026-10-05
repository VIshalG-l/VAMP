from flask import Flask, render_template, Response
import subprocess
import threading

app = Flask(__name__)

console_output = ""
process = None
lock = threading.Lock()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/run")
@app.route("/run/<bug>")
def run_pipeline(bug=None):
    """
    Start the generic VAMP Android diagnosis pipeline.

    The optional <bug> parameter is retained only for backward
    compatibility with older requests such as /run/anr or
    /run/display.

    The actual pipeline is always generic and starts main.py
    without a bug-specific argument.
    """

    global process
    global console_output

    if process is not None and process.poll() is None:
        return "Pipeline already running", 409

    with lock:
        console_output = ""

    def worker():

        global process
        global console_output

        try:

            process = subprocess.Popen(
                ["python3", "-u", "main.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            while True:

                line = process.stdout.readline()

                if (
                    line == ""
                    and process.poll() is not None
                ):
                    break

                if line:

                    print(
                        line,
                        end=""
                    )

                    with lock:
                        console_output += line

            process.stdout.close()
            process.wait()

        except Exception as exc:

            error_line = (
                "\n❌ Flask failed to start VAMP: "
                f"{exc}\n"
            )

            print(
                error_line,
                end=""
            )

            with lock:
                console_output += error_line

        finally:

            process = None

    threading.Thread(
        target=worker,
        daemon=True
    ).start()

    return "Started"


@app.route("/status")
def status():
    """
    Report the actual state of the main.py subprocess.

    This endpoint is used only by the UI to determine when
    terminal-output polling can stop.

    It does not affect the VAMP pipeline.
    """

    global process

    running = (
        process is not None
        and process.poll() is None
    )

    return {
        "running": running
    }


@app.route("/logs")
def logs():

    with lock:
        output = console_output

    return Response(
        output,
        mimetype="text/plain"
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )
