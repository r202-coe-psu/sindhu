import datetime
import os

from flask import current_app, url_for

# Version for static files that can't be found on disk: fixed for the life of
# the process, so their URLs still stay the same from page to page.
_STARTED = int(datetime.datetime.now().timestamp())


def static_url(filename: str):
    """URL of a static file with a cache-busting version.

    The version is the file's modification time, so the URL only changes when
    the file does and browsers can cache logos, CSS and JS between pages.
    (It used to be the current time, which made every page load fetch every
    asset again.)
    """
    path = os.path.join(current_app.static_folder, filename)
    try:
        version = int(os.path.getmtime(path))
    except OSError:
        version = _STARTED
    return f"{url_for('static', filename=filename)}?v={version}"


def format_date(date: datetime.datetime, formatter: str = "%d/%m/%Y"):
    return date.strftime(formatter)


def format_number(data: str | int | float, digits: int = 2):
    if digits == 0:
        return f"{data:,.0f}"
    else:
        return f"{data:,.{digits}f}"


def two_decimals(value):
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return value
