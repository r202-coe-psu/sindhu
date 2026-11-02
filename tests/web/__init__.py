from sindhu import web

_app = None


def shared_app():
    """One Flask app for every web test.

    The blueprints are module-level objects, so calling create_app() a second
    time in the same process fails while they are re-registered.
    """
    global _app
    if _app is None:
        _app = web.create_app()
        _app.config["APP_TITLE"] = "เฝ้าดู (FoundDoo)"
    return _app
