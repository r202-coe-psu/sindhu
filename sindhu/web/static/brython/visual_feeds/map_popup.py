"""Popup shown above a camera pin by the "ดูภาพล่าสุด" button.

Styling lives in setup.css under ``.cctv-map-popup``.
"""

from browser import document


def _el(tag, class_name, text=None):
    element = document.createElement(tag)
    element.className = class_name
    if text is not None:
        # Provider values always enter the DOM through textContent.
        element.textContent = text
    return element


def build_map_popup(title, image, status_label, status_class, on_expand):
    """``image`` is the camera's image view, or None when it has no image."""
    popup = _el("div", "cctv-map-popup")
    if image is None:
        popup <= _el("div", "cctv-map-popup__empty", "ไม่มีภาพล่าสุด")
    else:
        image.classList.add("cctv-map-popup__image")
        popup <= image
    popup <= _el("div", "cctv-map-popup__title", title)

    footer = _el("div", "cctv-map-popup__footer")
    footer <= _el("span", f"cctv-status {status_class}", status_label)
    expand_btn = _el("button", "btn btn-xs btn-primary", "ขยาย")
    expand_btn.attrs["type"] = "button"
    expand_btn.bind("click", on_expand)
    footer <= expand_btn
    popup <= footer
    return popup
