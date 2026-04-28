import datetime
from wtforms import (
    validators,
    StringField,
    FloatField,
    ValidationError,
    IntegerField,
    SelectField,
    DateField,
    fields,
)
from flask import (
    request,
)
from flask_wtf.file import FileAllowed
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, Length

from sindhu import models


class FireReportForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "Name"},
    )
    year = StringField(
        "Year",
        validators=[validators.InputRequired(), Length(min=4, max=4)],
        render_kw={"placeholder": f"{datetime.datetime.now().year}"},
    )
    enso_phase = StringField(
        "Enso Phase",
        render_kw={"placeholder": "Neutral"},
    )
    category = SelectField(
        "Category",
        default="FAHP",
        choices=[
            ("FAHP", "FAHP"),
            ("dNBR", "dNBR"),
            ("MLBA", "MLBA"),
            ("Emissions", "Emissions"),
        ],
    )
    status = SelectField(
        "Status",
        default="active",
        choices=[
            ("active", "active"),
            ("disactive", "disactive"),
        ],
    )

    file = fields.FileField(
        "Upload file",
        validators=[
            FileAllowed(
                ["json"],
                "Invalid file format. Please upload an Json file (.json) only.",
            )
        ],
    )

    def validate_file(self, field):
        if not field.data and not request.args.get("fire_report_id"):
            raise ValidationError("กรุณาอัปโหลดไฟล์เมื่อสร้างรายงานใหม่")


class FireReportFileForm(FlaskForm):
    file = fields.FileField(
        "Upload file",
        validators=[
            FileAllowed(
                ["json"],
                "Invalid file format. Please upload an Json file (.json) only.",
            )
        ],
    )


class FireReportSearchForm(FlaskForm):
    year = StringField()
    category = SelectField(
        "Category",
        default="Unselected",
        choices=[
            ("Unselected", "Unselected"),
            ("FAHP", "FAHP"),
            ("dNBR", "dNBR"),
            ("MLBA", "MLBA"),
            ("Emissions", "Emissions"),
        ],
    )
    status = SelectField(
        "Status",
        default="active",
        choices=[
            ("active", "active"),
            ("disactive", "disactive"),
        ],
    )
