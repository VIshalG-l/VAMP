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


@app.route("/run/<bug>")
def run_pipeline(bug):

    global process
    global console_output

    if process is not None and process.poll() is None:
        return "Pipeline already running"

    console_output = ""

    choice = "1" if bug.lower() == "anr" else "2"

    def worker():

        global process
        global console_output

        process = subprocess.Popen(
            ["python3", "-u", "main.py", choice],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        while True:

            line = process.stdout.readline()

            if line == "" and process.poll() is not None:
                break

            if line:

                print(line, end="")

                with lock:
                    console_output += line

        process.stdout.close()
        process.wait()

    threading.Thread(
        target=worker,
        daemon=True
    ).start()

    return "Started"


@app.route("/logs")
def logs():

    with lock:
        return Response(console_output, mimetype="text/plain")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )
