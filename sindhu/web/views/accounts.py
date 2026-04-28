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

from .. import oauth2
from .. import forms
from . import paginations

from .. import sindhu_api_clients
from .. import models as sindhu_web_models

from sindhu_client import models
from sindhu_client.api.v1 import (
    authentication_v1_auth_login_post,
    get_me_v1_users_me_get,
    refresh_token_v1_auth_refresh_token_get,
    get_all_v1_users_get,
    get_v1_users_user_id_get,
    create_v1_users_create_post,
    update_v1_users_user_id_update_put,
    set_role_v1_users_user_id_set_role_put,
    set_status_v1_users_user_id_set_status_put,
)


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
    # expires_at = datetime.datetime.fromisoformat(session["tokens"]["expires_at"])
    # if expires_at > datetime.datetime.now():
    #     print("token expired")
    #     client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
    #     response = refresh_token_v1_auth_refresh_token_get.sync_detailed(
    #         client=client, credentials=session["tokens"]["refresh_token"]
    #     )
    #     token = response

    return jsonify(token)


@module.route("/login/<name>")
def login_oauth(name):
    client = oauth2.oauth2_client

    scheme = request.environ.get("HTTP_X_FORWARDED_PROTO", "http")
    redirect_uri = url_for(
        "users.authorized_oauth", name=name, _external=True, _scheme=scheme
    )
    response = None
    if name == "google":
        response = client.google.authorize_redirect(redirect_uri)
    elif name == "facebook":
        response = client.facebook.authorize_redirect(redirect_uri)
    elif name == "line":
        response = client.line.authorize_redirect(redirect_uri)
    elif name == "psu":
        response = client.psu.authorize_redirect(redirect_uri)
    elif name == "engpsu":
        response = client.engpsu.authorize_redirect(redirect_uri)
    return response


@module.route("/auth/sindhu", methods=["POST"])
def authorized_sindhu():
    form = forms.users.LoginForm()
    if not form.validate_on_submit():
        return redirect("accounts.login")

    username = form.username.data
    password = form.password.data

    model = (
        models.body_authentication_v1_auth_login_post.BodyAuthenticationV1AuthLoginPost(
            username=username, password=password
        )
    )

    client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
    response = authentication_v1_auth_login_post.sync(client=client, body=model)

    if not response:
        return redirect(url_for("accounts.login"))

    session["tokens"] = response.to_dict()

    client = sindhu_api_clients.client.get_current_client()
    response = get_me_v1_users_me_get.sync(client=client)

    user = sindhu_web_models.users.User(response.to_dict())
    login_user(user)
    session["me"] = response.to_dict()

    return redirect(url_for("sites.index"))


@module.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()

    return redirect(url_for("sites.home"))


@module.route("/accounts/management", methods=["GET", "POST"])
def management():
    form = forms.SearchUserForm()
    email = request.args.get("email", None)
    username = request.args.get("username", None)
    page = int(request.args.get("page", default=1))

    client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
    response = get_all_v1_users_get.sync(client=client, current_page=page)

    if email or username:
        response = get_all_v1_users_get.sync(
            client=client,
            current_page=page,
            email=email,
            username=username,
        )

    form.email.data = email
    form.username.data = username

    users = response.users
    pagination = paginations.get_paginates(
        data=users, count=response.count, current_page=response.current_page
    )
    return render_template(
        "accounts/management.html",
        form=form,
        users=pagination["data"],
        pagination=pagination,
        page=page,
    )


@module.route("/create_update", methods=["GET", "POST"])
def create_update():
    user = None
    user_id = request.args.get("user_id", "")
    client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
    if user_id:
        user = get_v1_users_user_id_get.sync(client=client, user_id=user_id)
    form = forms.UserForm()

    if not form.validate_on_submit():
        if user:
            form.username.data = user.username
            form.first_name.data = user.first_name
            form.last_name.data = user.last_name
            form.email.data = user.email
            form.password.data = user.password
            form.confirm_password.data = user.confirm_password

        return render_template(
            "/accounts/create_update.html",
            form=form,
            user=user,
        )
    form_data = form.data

    user_body = models.RegisteredUser(
        username=form_data["username"],
        email=form_data["email"],
        first_name=form_data["first_name"],
        last_name=form_data["last_name"],
        password=form_data["password"],
        confirm_password=form_data["confirm_password"],
    )

    if user:
        db_user = update_v1_users_user_id_update_put.sync_detailed(
            client=client, user_id=user_id, body=user_body
        )
    else:
        db_user = create_v1_users_create_post.sync_detailed(
            client=client, body=user_body
        )
    if not db_user:
        render_template(
            "/accounts/create_update.html",
            form=form,
            user=user,
            message="Error can't save station data.",
        )
    return redirect(url_for("accounts.management"))


@module.route("/accounts/<user_id>/grant_role/<role>", methods=["GET", "POST"])
def grant_role(user_id, role):
    user = None
    page = int(request.args.get("page", 1))
    client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
    if user_id:
        user = get_v1_users_user_id_get.sync(client=client, user_id=user_id)
    if role in user.roles:
        user = set_role_v1_users_user_id_set_role_put.sync(
            client=client, user_id=user_id, role=role, action="remove"
        )
    else:
        user = set_role_v1_users_user_id_set_role_put.sync(
            client=client, user_id=user_id, role=role, action="add"
        )
    return redirect(url_for("accounts.management", page=page))


@module.route("/accounts/<user_id>/delete", methods=["GET", "POST"])
def delete_user(user_id):
    page = int(request.args.get("page", 1))
    client = sindhu_api_clients.client.get_current_client(is_anonymous=True)
    if user_id:
        user = set_status_v1_users_user_id_set_status_put.sync(
            client=client, user_id=user_id, status="disactive"
        )

    return redirect(url_for("accounts.management", page=page))


@module.route("/users/<user_id>")
def profile(user_id):
    return index()


@module.route("/users", methods=["GET", "POST"])
@login_required
def index():
    biography = ""
    # if current_user.biography:
    #     biography = markdown.markdown(current_user.biography)

    # form = forms.users.SelectOrganizationForm(obj=current_user.user_setting)
    # form.current_organization.choices = [
    #     (str(o.id), o.name) for o in current_user.organizations
    # ]

    # if form.validate_on_submit():
    # current_user.user_setting.current_organization = (
    #     models.Organization.objects.get(id=form.current_organization.data)
    # )
    # current_user.save()
    # return redirect(url_for("users.index"))

    # current_organization = current_user.user_setting.current_organization
    # if current_organization:
    #     form.current_organization.data = str(current_organization.id)

    form = forms.users.UserForm()
    return render_template(
        "/users/index.html", user=current_user, biography=biography, form=form
    )


@module.route("/users/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = forms.users.ProfileForm(obj=current_user, pic=current_user.picture)
    if not form.validate_on_submit():
        return render_template("/users/edit-profile.html", form=form)

    user = current_user._get_current_object()
    form.populate_obj(user)

    if form.pic.data:
        if user.picture:
            user.picture.replace(
                form.pic.data,
                filename=form.pic.data.filename,
                content_type=form.pic.data.content_type,
            )
        else:
            user.picture.put(
                form.pic.data,
                filename=form.pic.data.filename,
                content_type=form.pic.data.content_type,
            )

    user.updated_date = datetime.datetime.now()
    user.save()

    return redirect(url_for("users.index"))


@module.route("/users/<user_id>/picture/<filename>", methods=["GET", "POST"])
def picture(user_id, filename):
    user = models.User.objects.get(id=user_id)

    if not user or not user.picture or user.picture.filename != filename:
        return abort(403)

    response = send_file(
        user.picture,
        download_name=user.picture.filename,
        mimetype=user.picture.content_type,
    )
    return response


@module.route(
    "/users/<user_id>/add-signature",
    methods=["GET", "POST"],
    defaults={"signature_id": None},
)
@module.route("/users/<user_id>/signatures/<signature_id>", methods=["GET", "POST"])
def add_or_edit_signature(user_id, signature_id):
    user = models.User.objects.get(id=user_id)

    form = forms.signatures.SignatureForm()
    if signature_id:
        signature = models.Signature.objects(id=signature_id).first()
        form = forms.signatures.SignatureForm(obj=signature)

    if not form.validate_on_submit():
        return render_template(
            "/users/add-signature.html",
            form=form,
        )

    if not signature_id:
        signature = models.Signature(
            owner=current_user._get_current_object(),
            ip_address=request.remote_addr,
        )

        signature.file.put(
            form.signature_file.data,
            filename=form.signature_file.data.filename,
            content_type=form.signature_file.data.content_type,
        )
    else:
        signature.file.replace(
            form.signature_file.data,
            filename=form.signature_file.data.filename,
            content_type=form.signature_file.data.content_type,
        )

    signature.last_updated_by = current_user._get_current_object()
    signature.updated_date = datetime.datetime.now()
    signature.ip_address = request.remote_addr
    signature.save()

    return redirect(url_for("users.profile", user_id=user_id))


@module.route("/change_organization/<organization_id>")
def change_organization(organization_id):
    user = current_user._get_current_object()
    organization = models.Organization.objects.get(id=organization_id)
    if organization in user.organizations:
        user.user_setting.current_organization = organization
        user.user_setting.updated_date = datetime.datetime.now()
        user.save()

    return redirect(url_for("dashboard.index"))
