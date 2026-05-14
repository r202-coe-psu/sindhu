from flask import Blueprint, render_template

module = Blueprint("sites", __name__)

@module.route("/")
def index():
    return render_template("sites/index.html")

@module.route("/monitor")
def monitor():
    return render_template("sites/monitor.html")
