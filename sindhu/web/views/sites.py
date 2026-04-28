from flask import Blueprint, render_template, redirect, url_for, g, request, current_app
from flask_login import current_user
import datetime
from sindhu import models
from pathlib import Path
from .. import caches

from .. import dhara_api_clients
from .. import models as sindhu_web_models

from dhara_client import models
from dhara_client.api.v1 import all_v1_climate_formulas_get

module = Blueprint("sites", __name__)


@caches.cache.cached(timeout=600)
@module.route("/home")
def home():

    return redirect(url_for("dashboard.new"))
    # climate_formulas = None
    # client = dhara_api_clients.client.get_current_client(is_anonymous=True)

    # response = all_v1_climate_formulas_get.sync(
    #     client=client, status="active", source="PCD"
    # )

    # if response:
    #     response = response.to_dict()
    #     climate_formulas = response["climate_formulas"]
    # source = "air4thai"

    # return render_template(
    #     "sites/home.html",
    #     climate_formulas=climate_formulas,
    #     api_url=current_app.config.get("SINDHU_API_BASE_URL"),
    #     source=source,
    # )


@caches.cache.cached(timeout=600)
@module.route("/home_page")
def home_page():

    climate_formulas = None
    client = dhara_api_clients.client.get_current_client(is_anonymous=True)

    response = all_v1_climate_formulas_get.sync(
        client=client, status="active", source="PCD"
    )

    if response:
        response = response.to_dict()
        climate_formulas = response["climate_formulas"]
    source = "air4thai"

    return render_template(
        "sites/home.html",
        climate_formulas=climate_formulas,
        api_url=current_app.config.get("SINDHU_API_BASE_URL"),
        source=source,
    )


@caches.cache.cached(timeout=600)
@module.route("/")
def index():
    climate_formulas = None
    if not current_user.is_authenticated:
        return redirect(url_for("sites.home"))

    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    response = all_v1_climate_formulas_get.sync(
        client=client, status="active", source="PCD"
    )

    if response:

        response = response.to_dict()
        climate_formulas = response["climate_formulas"]

    source = "air4thai"
    return render_template(
        "sites/index.html",
        api_url=current_app.config.get("SINDHU_API_BASE_URL"),
        climate_formulas=climate_formulas,
        source=source,
        # viir_hotspots=viir_hotspots,
        # modis_hotspots=modis_hotspots,
        # system_setting=system_setting.to_json(),
    )


# @caches.cache.cached(timeout=600)
@module.route("/empirical_forecast")
def empirical_forecast():
    predict_date = datetime.datetime.now()
    predict_date = predict_date.replace(hour=0, minute=0, second=0, microsecond=0)
    predict_days = []
    for i in range(0, 5):
        predict_days.append(predict_date + datetime.timedelta(days=i + 1))

    climate_formulas = None
    if not current_user.is_authenticated:
        return redirect(url_for("sites.home"))

    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    response = all_v1_climate_formulas_get.sync(
        client=client, status="active", source="PCD"
    )

    if response:

        response = response.to_dict()
        climate_formulas = response["climate_formulas"]

    source = "air4thai"

    return render_template(
        "sites/empirical_forecasts.html",
        api_url=current_app.config.get("SINDHU_API_BASE_URL"),
        climate_formulas=climate_formulas,
        source=source,
        predict_days=predict_days,
        # viir_hotspots=viir_hotspots,
        # modis_hotspots=modis_hotspots,
        # system_setting=system_setting.to_json(),
    )


@caches.cache.cached(timeout=600)
@module.route("/fire_hotspots")
def fire_hotspots():
    if not current_user.is_authenticated:
        return redirect(url_for("accounts.login"))

    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    source = "firms"

    return render_template(
        "sites/fire_hotspots.html",
        api_url=current_app.config.get("SINDHU_API_BASE_URL"),
        source=source,
    )


# @caches.cache.cached(timeout=600)
@module.route("/fire_reports")
def fire_reports():
    if not current_user.is_authenticated:
        return redirect(url_for("accounts.login"))

    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    source = "fire_reports"
    center = [100.025311, 8.016964]
    zoom = 11

    return render_template(
        "sites/fire_reports.html",
        api_url=current_app.config.get("SINDHU_API_BASE_URL"),
        source=source,
        center=center,
        zoom=zoom,
    )


@module.route("/change_lang")
def change_lang():
    lang_code = "th"
    if "/en/" in request.path:
        lang_code = "en"

    url = request.referrer
    if lang_code == "th":
        g.lang_code = "en"
        url = url.replace("/th/", "/en/")
    else:
        g.lang_code = "th"
        url = url.replace("/en/", "/th/")
    return redirect(url)


@module.route("/list_shape")
# @login_required
def list_shape():
    # list the shape tree (return dict)
    path = (
        Path(__file__).parent / "../static/brython/maps/resources/geojsons"
    )  # join path

    # dig down directory untill there are no directory. return dict (directory tree)
    def walk_directory(path):  # recursive funciton
        data = {}
        for p in path.iterdir():
            if p.is_dir():
                data[p.stem] = walk_directory(p)
            else:
                data[p.stem] = p.stem
        return data

    if path.exists():
        return walk_directory(path)

    return {}


@module.route("/privacy-policy")
def privacy_policy():
    return render_template("base/privacy-policy.html")
