from wtforms import (
    validators,
    StringField,
    FloatField,
    ValidationError,
    IntegerField,
    DateTimeField,
)
from flask_wtf import FlaskForm
from .fields import GeoField


class SystemSettingForm(FlaskForm):
    center = GeoField(default=[0, 0], validators=[validators.InputRequired()])
    zoom = IntegerField(default=5, validators=[validators.InputRequired()])
    min_zoom = IntegerField(default=2, validators=[validators.InputRequired()])
    interpolation_coordinate_1 = GeoField(
        "Interpolation coordinate 1",
        default=[0, 0],
        validators=[validators.InputRequired()],
    )
    interpolation_coordinate_2 = GeoField(
        "Interpolation coordinate 2",
        default=[0, 0],
        validators=[validators.InputRequired()],
    )


class ApiForm(FlaskForm):
    def strip_string(string):
        if string is not None and hasattr(string, "strip"):
            return string.strip()
        return string

    def validate_name(form, field):
        if "__" in field.data:
            raise ValidationError('Field must not contain "__" (Double Underscore)')

    source = StringField(
        "Source URL", validators=[validators.DataRequired()], filters=[strip_string]
    )
    access_token = StringField("Access Token")
    access_token_expires = DateTimeField(
        "Access Token Expires (UCT Time)",
        [validators.Optional()],
        render_kw={"placeholder": "YYYY-MM-DD HH:mm:ss"},
    )
    refresh_token = StringField("Refresh Token")
    refresh_token_expires = DateTimeField(
        "Refresh Token Expires (UTC Time)",
        [validators.Optional()],
        render_kw={"placeholder": "YYYY-MM-DD HH:mm:ss"},
    )
