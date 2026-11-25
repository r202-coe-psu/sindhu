from flask import Blueprint, current_app, redirect, render_template, url_for

module = Blueprint("sites", __name__)


@module.route("/")
def index():
    api_url = current_app.config.get("SINDHU_API_BASE_URL")
    default_source = "all"
    return render_template(
        "sites/monitor.html",
        api_url=api_url,
        source=default_source,
    )


@module.route("/monitor")
def monitor():
    return redirect(url_for("sites.index"), code=301)
