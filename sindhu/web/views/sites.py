from flask import Blueprint, render_template, current_app

module = Blueprint("sites", __name__)

@module.route("/")
def index():
    return render_template("sites/index.html")

@module.route("/monitor")
def monitor():
    api_url = current_app.config.get("SINDHU_API_BASE_URL")
    default_source = "all"
    return render_template(
        "sites/monitor.html",
        api_url=api_url,
        source=default_source,
    )
