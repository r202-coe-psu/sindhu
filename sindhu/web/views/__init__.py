import datetime
import pathlib
import importlib
import logging
from flask import g, redirect, url_for
from sindhu.web.utils import template_filters


logger = logging.getLogger(__name__)


def add_date_url(url):
    now = datetime.datetime.now()
    return f'{url}?date={now.strftime("%Y%m%d")}'


def get_subblueprints(directory):
    blueprints = []

    package = directory.parts[len(pathlib.Path.cwd().parts) :]
    parent_module = None
    try:
        parrent_view = directory.with_name("__init__.py")
        pymod_file = f"{'.'.join(package)}"
        pymod = importlib.import_module(pymod_file)

        if "module" in dir(pymod):
            parent_module = pymod.module
            blueprints.append(parent_module)
    except Exception as e:
        logger.exception(e)
        return blueprints

    subblueprints = []
    for module in directory.iterdir():
        if "__" == module.name[:2]:
            continue

        if module.match("*.py"):
            try:
                pymod_file = f"{'.'.join(package)}.{module.stem}"
                pymod = importlib.import_module(pymod_file)

                if "module" in dir(pymod):
                    subblueprints.append(pymod.module)
            except Exception as e:
                logger.exception(e)

        elif module.is_dir():
            subblueprints.extend(get_subblueprints(module))

    for module in subblueprints:
        if parent_module:
            parent_module.register_blueprint(module)
        else:
            blueprints.append(module)

    return blueprints


def register_blueprint(app):
    app.add_template_filter(add_date_url)
    app.add_template_filter(template_filters.static_url)
    app.add_template_filter(template_filters.format_date)
    app.add_template_filter(template_filters.format_number)
    app.add_template_filter(template_filters.two_decimals)
    parent = pathlib.Path(__file__).parent
    blueprints = get_subblueprints(parent)

    @app.route("/")
    def index():
        if not hasattr(g, "lang_code"):
            return redirect(url_for("sites.index", lang_code="th"))
        return redirect(url_for("sites.index", lang_code=g.lang_code))

    for blueprint in blueprints:

        @blueprint.url_defaults
        def add_language_code(endpoint, values):
            if "lang_code" in values or not g.lang_code:
                return
            if app.url_map.is_endpoint_expecting(endpoint, "lang_code"):
                values["lang_code"] = g.lang_code

        @blueprint.url_value_preprocessor
        def pull_lang_code(endpoint, values):
            g.lang_code = values.pop("lang_code")

        app.register_blueprint(
            blueprint,
            url_prefix=f"/<lang_code>{blueprint.url_prefix if blueprint.url_prefix else ''}",
        )
