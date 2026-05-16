from flask import Blueprint, render_template, redirect, url_for
from sindhu import models
from sindhu.web import acl, sindhu_api_clients
from sindhu.web import forms
from datetime import datetime

import sindhu_client.models as sindhu_client_models

from sindhu_client.api.v1 import (
    get_v1_system_settings_get,
    create_v1_system_settings_create_post,
    update_v1_system_settings_update_put,
    create_api_token_v1_system_settings_api_tokens_create_post
)

module = Blueprint("system_settings", __name__, url_prefix="/system_settings")

@module.route("/", methods=["GET", "POST"])
@acl.roles_required("admin")
def index():
    system_setting = None
    client = sindhu_api_clients.client.get_current_client(is_anonymous=False)
    response = get_v1_system_settings_get.sync(client=client)
    if response:
        system_setting = response.to_dict()

    form = forms.system_settings.SystemSettingForm()
    if not form.validate_on_submit():
        if system_setting:
            form.center.data = system_setting["center"]["coordinates"]
            form.zoom.data = system_setting["zoom"]
            form.min_zoom.data = system_setting["min_zoom"]
            if system_setting["interpolation_coordinate_1"]:
                form.interpolation_coordinate_1.data = system_setting[
                    "interpolation_coordinate_1"
                ]["coordinates"]
            if system_setting["interpolation_coordinate_2"]:
                form.interpolation_coordinate_2.data = system_setting[
                    "interpolation_coordinate_2"
                ]["coordinates"]
        return render_template(
            "/system_settings/index.html",
            form=form,
            system_setting=system_setting,
        )

    center = sindhu_client_models.GeoObject.from_dict(
        {"type": "Point", "coordinates": form.center.data}
    )
    interpolation_coordinate_1 = sindhu_client_models.GeoObject.from_dict(
        {"type": "Point", "coordinates": form.interpolation_coordinate_1.data}
    )
    interpolation_coordinate_2 = sindhu_client_models.GeoObject.from_dict(
        {"type": "Point", "coordinates": form.interpolation_coordinate_2.data}
    )

    if not system_setting:
        system_setting_body = sindhu_client_models.CreateSystemSetting.from_dict(
            {
                "center": center.to_dict(),
                "zoom": form.zoom.data,
                "min_zoom": form.min_zoom.data,
                "interpolation_coordinate_1": interpolation_coordinate_1.to_dict(),
                "interpolation_coordinate_2": interpolation_coordinate_2.to_dict(),
            }
        )
        response = create_v1_system_settings_create_post.sync(
            client=client, body=system_setting_body
        )
    else:
        system_setting_body = sindhu_client_models.UpdateSystemSetting.from_dict(
            {
                "center": center.to_dict(),
                "zoom": form.zoom.data,
                "min_zoom": form.min_zoom.data,
                "interpolation_coordinate_1": interpolation_coordinate_1.to_dict(),
                "interpolation_coordinate_2": interpolation_coordinate_2.to_dict(),
            }
        )
        response = update_v1_system_settings_update_put.sync(
            client=client, body=system_setting_body
        )
    if not response:
        print("error cannot save")

    return redirect(url_for("system_settings.index"))

@module.route("/api_tokens/add/", methods=["GET", "POST"])
@acl.roles_required("admin")
def add_api_token():
    form = forms.system_settings.ApiForm()

    if not form.validate_on_submit():
        return render_template("system_settings/index.html", form=form)

    api_token_body = sindhu_client_models.CreateUpdateApiToken.from_dict(
        {
            "source": form.source.data,
            "access_token": form.access_token.data,
            "access_token_expires": form.access_token_expires.data,
            "refresh_token": form.refresh_token.data,
            "refresh_token_expires": form.refresh_token_expires.data,
        }
    )
    client = sindhu_api_clients.client.get_current_client(is_anonymous=False)
    response = create_api_token_v1_system_settings_api_tokens_create_post.sync(
        client=client, body=api_token_body
    )

    return redirect(url_for("system_settings.index"))

