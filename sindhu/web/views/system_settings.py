from flask import Blueprint, render_template, redirect, url_for
from sindhu import models
from sindhu.web import forms, acl
import datetime

from dhara_client import models
from .. import dhara_api_clients
from .. import models as sindhu_web_models

from dhara_client.api.v1 import (
    get_v1_system_settings_get,
    update_v1_system_settings_update_put,
    create_v1_system_settings_create_post,
    create_api_token_v1_system_settings_api_tokens_create_post,
    delete_api_token_v1_system_settings_api_tokens_delete_api_token_id_delete,
    get_api_token_v1_system_settings_api_tokens_get_api_token_id_get,
    update_api_token_v1_system_settings_api_tokens_update_api_token_id_put,
)

# from mongoengine import Q

# from pinform.client import AggregationMode

module = Blueprint("system_settings", __name__, url_prefix="/system_settings")


@module.route("/", methods=["GET", "POST"])
@acl.roles_required("admin")
def index():
    system_setting = None
    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    response = get_v1_system_settings_get.sync(client=client)
    if response:
        system_setting = response.to_dict()

    form = forms.SystemSettingForm()
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

    center = models.GeoObject(type_="Point", coordinates=form.center.data)
    interpolation_coordinate_1 = models.GeoObject(
        type_="Point", coordinates=form.interpolation_coordinate_1.data
    )
    interpolation_coordinate_2 = models.GeoObject(
        type_="Point", coordinates=form.interpolation_coordinate_2.data
    )

    if not system_setting:
        system_setting_body = models.CreateSystemSetting(
            center=center,
            zoom=form.zoom.data,
            min_zoom=form.min_zoom.data,
            interpolation_coordinate_1=interpolation_coordinate_1,
            interpolation_coordinate_2=interpolation_coordinate_2,
            # api_tokens=[],
        )
        response = create_v1_system_settings_create_post.sync(
            client=client, body=system_setting_body
        )
    else:
        system_setting_body = models.UpdateSystemSetting(
            center=center,
            zoom=form.zoom.data,
            min_zoom=form.min_zoom.data,
            interpolation_coordinate_1=interpolation_coordinate_1,
            interpolation_coordinate_2=interpolation_coordinate_2,
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
    form = forms.ApiForm()

    if not form.validate_on_submit():
        return render_template("system_settings/api.html", form=form)

    api_token_body = models.CreateUpdateApiToken(
        source=form.source.data,
        access_token=form.access_token.data,
        access_token_expires=form.access_token_expires.data,
        refresh_token=form.refresh_token.data,
        refresh_token_expires=form.refresh_token_expires.data,
    )
    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    response = create_api_token_v1_system_settings_api_tokens_create_post.sync(
        client=client, body=api_token_body
    )

    return redirect(url_for("system_settings.index"))


@module.route("/api/edit/<api_token_id>/", methods=["GET", "POST"])
@acl.roles_required("admin")
def edit_api_token(api_token_id):
    form = forms.ApiForm()

    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    api_token = None
    if api_token_id:
        api_token = (
            get_api_token_v1_system_settings_api_tokens_get_api_token_id_get.sync(
                client=client, api_token_id=api_token_id
            )
        )
        form = forms.ApiForm(obj=api_token)

    if not form.validate_on_submit():
        return render_template("system_settings/api.html", form=form)

    data = form.data.copy()
    response = None
    if api_token:
        api_token = models.CreateUpdateApiToken.from_dict(data)
        response = (
            update_api_token_v1_system_settings_api_tokens_update_api_token_id_put.sync(
                client=client, api_token_id=api_token_id, body=api_token
            )
        )

    if not response:
        print("error cannot save")

    return redirect(url_for("system_settings.index"))


@module.route("/api/remove/<api_token_id>/")
@acl.roles_required("admin")
def remove_api_token(api_token_id):
    client = dhara_api_clients.client.get_current_client(is_anonymous=True)
    response = (
        delete_api_token_v1_system_settings_api_tokens_delete_api_token_id_delete.sync(
            client=client, api_token_id=api_token_id
        )
    )
    return redirect(url_for("system_settings.index"))
