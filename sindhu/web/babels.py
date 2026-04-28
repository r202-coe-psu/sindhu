from flask_babel import Babel
from flask import g, request, current_app

babel = Babel()


def init_babel(app):
    babel.init_app(app, locale_selector=get_locale)


def get_locale():
    if not g.get("lang_code", None):
        g.lang_code = request.accept_languages.best_match(
            current_app.config["LANGUAGES"]
        )
    return g.lang_code
