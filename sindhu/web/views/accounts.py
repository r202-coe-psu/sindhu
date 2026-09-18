import datetime
import json
from urllib.parse import urlparse

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


def safe_next_url(value):
    """Keep a post-login redirect on this site, whatever `next` was given."""
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.netloc and parsed.netloc != request.host:
        return None
    path = parsed.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return None
    return f"{path}?{parsed.query}" if parsed.query else path


def token_expired(expires_at):
    expires_at = datetime.datetime.fromisoformat(expires_at)
    if expires_at.tzinfo:
        return expires_at <= datetime.datetime.now(datetime.timezone.utc)
    return expires_at <= datetime.datetime.now()


@module.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("sites.index"))

    if "next" in request.args:
        session["next"] = safe_next_url(request.args.get("next"))

    oauth_clients = current_app.extensions["authlib.integrations.flask_client"]._clients

    form = forms.users.LoginForm()

    return render_template(
        "/accounts/login.html", oauth_clients=oauth_clients, form=form
    )


def end_expired_session():
    """The API no longer accepts this session's tokens; make the user log in again."""
    logout_user()
    session.clear()
    return jsonify({"detail": "Session expired, please log in again"}), 401


@module.route("/get_token", methods=["GET"])
@login_required
def get_token():
    tokens = session.get("tokens") or {}
    if not tokens.get("access_token") or not tokens.get("expires_at"):
        return end_expired_session()

    if token_expired(tokens["expires_at"]):
        logger.info("API access token expired, refreshing")
        client = AuthenticatedClient(
            base_url=str(current_app.config.get("SINDHU_API_BASE_URL")),
            token=str(tokens.get("refresh_token")),
        )
        try:
            response = refresh_token_v1_auth_refresh_token_get.sync_detailed(
                client=client
            )
        except Exception as e:
            logger.exception(f"Refresh token request failed: {e}")
            return end_expired_session()

        # The generated client leaves `parsed` empty for this endpoint, so read
        # the body directly
        if response.status_code != 200:
            logger.info(f"Refresh token rejected: HTTP {response.status_code}")
            return end_expired_session()

        refreshed = json.loads(response.content)
        # Keep the refresh token: the refresh response only renews the access token
        tokens.update(
            access_token=refreshed["access_token"],
            expires_at=refreshed["expires_at"],
            token_type=refreshed.get("token_type", tokens.get("token_type")),
        )
        session["tokens"] = tokens

    return jsonify(
        {
            "access_token": tokens["access_token"],
            "expires_at": tokens["expires_at"],
            "token_type": tokens.get("token_type"),
        }
    )


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

    return redirect(safe_next_url(session.pop("next", None)) or url_for("sites.index"))


# No login_required: an expired session is sent here to be cleared, and forcing a
# login first would log the user straight back out afterwards
@module.route("/logout")
def logout():
    logout_user()
    session.clear()

    next_url = safe_next_url(request.args.get("next"))
    if next_url:
        return redirect(url_for("accounts.login", next=next_url))
    return redirect(url_for("sites.index"))
