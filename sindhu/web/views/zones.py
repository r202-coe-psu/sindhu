from flask import Blueprint, render_template, current_app

from sindhu.web import acl

module = Blueprint("zones", __name__, url_prefix="/zones")


@module.route("/")
@acl.roles_required("admin")
def index():
    api_url = current_app.config.get("SINDHU_API_BASE_URL")
    return render_template("zones/index.html", api_url=api_url)
