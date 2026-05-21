import datetime

from flask import (
    Blueprint,
    render_template,
    url_for,
    redirect,
    request,
    session,
    current_app,
    send_file,
    abort,
    jsonify,
)
from flask_login import login_user, logout_user, login_required, current_user
from ..models.users import User as WebUser

from .. import oauth2
from .. import forms
from . import paginations

from sindhu.web import sindhu_api_clients

from sindhu_client import models as sindhu_client_models, AuthenticatedClient

from sindhu_client.api.v1 import (
    authentication_v1_auth_login_post,
    refresh_token_v1_auth_refresh_token_get,
    get_me_v1_users_me_get,
)
import logging

logger = logging.getLogger(__name__)


module = Blueprint("accounts", __name__)


@module.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if "next" in request.args:
        session["next"] = request.args.get("next", None)

    oauth_clients = current_app.extensions["authlib.integrations.flask_client"]._clients

    form = forms.users.LoginForm()

    return render_template(
        "/accounts/login.html", oauth_clients=oauth_clients, form=form
    )


@module.route("/get_token", methods=["GET"])
@login_required
def get_token():
    token = {
        "access_token": session["tokens"]["access_token"],
        "expires_at": session["tokens"]["expires_at"],
        "token_type": session["tokens"]["token_type"],
    }
    expires_at = datetime.datetime.fromisoformat(session["tokens"]["expires_at"])
    if expires_at < datetime.datetime.now():
        print("token expired")
        client = AuthenticatedClient(
            base_url=str(current_app.config.get("SINDHU_API_BASE_URL")), 
            token=str(session["tokens"]["refresh_token"]),  
        )
        response = refresh_token_v1_auth_refresh_token_get.sync_detailed(client=client)
        if response.parsed:
            session["tokens"] = response.parsed.to_dict()
            token = session["tokens"]

    return jsonify(token)


@module.route("/login/<name>")
def login_oauth(name):
    client = oauth2.oauth2_client

    scheme = request.environ.get("HTTP_X_FORWARDED_PROTO", "http")
    redirect_uri = url_for(
        "users.authorized_oauth", name=name, _external=True, _scheme=scheme
    )
    if name == "google":
        return client.google.authorize_redirect(redirect_uri)
    elif name == "facebook":
        return client.facebook.authorize_redirect(redirect_uri)
    elif name == "line":
        return client.line.authorize_redirect(redirect_uri)
    elif name == "psu":
        return client.psu.authorize_redirect(redirect_uri)
    elif name == "engpsu":
        return client.engpsu.authorize_redirect(redirect_uri)
    return abort(404)


@module.route("/auth/sindhu", methods=["POST"])
def authorized_sindhu():
    form = forms.users.LoginForm()
    if not form.validate_on_submit():
        logger.error(f"Login failed: {form.errors}")
        return redirect(url_for("accounts.login"))

    username = form.username.data
    password = form.password.data
    try:
        client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
        body = sindhu_client_models.BodyAuthenticationV1AuthLoginPost.from_dict(
            {"username": username, "password": password}
        )
        response = authentication_v1_auth_login_post.sync(client=client, body=body)
    except Exception as e:
        logger.exception(f"Login failed: {e}")
        return redirect(url_for("accounts.login"))

    if not response:
        return redirect(url_for("accounts.login"))

    session["tokens"] = response.to_dict()

    client = sindhu_api_clients.client.get_current_client()
    response = get_me_v1_users_me_get.sync(client=client)

    if not response:
        return redirect(url_for("accounts.login"))

    user = WebUser(response.to_dict())
    login_user(user)
    session["me"] = response.to_dict()

    return redirect(url_for("sites.index"))


@module.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()

    return redirect(url_for("sites.index"))


