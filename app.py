import os

from flask import Flask, render_template

app = Flask(__name__)

APP_TITLE = os.environ.get("APP_TITLE", "ClusterKeep")


@app.get("/")
def index():
    return render_template("index.html", title=APP_TITLE)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
