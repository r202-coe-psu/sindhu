from flask import redirect, url_for, request, session
from flask_login import current_user, LoginManager, login_url
from werkzeug.exceptions import Forbidden, Unauthorized

from functools import wraps

from . import models

login_manager = LoginManager()


def init_acl(app):
    login_manager.init_app(app)

    @app.errorhandler(401)
    def unauthorized(e):
        return Unauthorized()

    @app.errorhandler(403)
    def forbidden(e):
        return "You don't have permission."


def roles_required(*roles):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                raise Unauthorized()

            for role in roles:
                if role in current_user.roles:
                    return func(*args, **kwargs)
            raise Forbidden()

        return wrapped

    return wrapper


@login_manager.user_loader
def load_user(user_id):
    me = session.get("me")
    user = models.users.User(me)
    return user


@login_manager.unauthorized_handler
def unauthorized_callback():
    if request.method == "GET":
        response = redirect(login_url("accounts.login", request.url))
        return response

    return redirect(url_for("accounts.login"))
