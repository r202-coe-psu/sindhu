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
from flask_wtf.file import FileAllowed
from flask_wtf import FlaskForm


class ClimateRecordForm(FlaskForm):
    month = SelectField(
        "Month",
        default=str(datetime.datetime.now().month),
        choices=[
            ("1", "มกราคม"),
            ("2", "กุมภาพันธ์"),
            ("3", "มีนาคม"),
            ("4", "เมษายน"),
            ("5", "พฤษภาคม"),
            ("6", "มิถุนายน"),
            ("7", "กรกฏาคม"),
            ("8", "สิงหาคม"),
            ("9", "กันยายน"),
            ("10", "ตุลาคม"),
            ("11", "พฤศจิกายน"),
            ("12", "ธันวาคม"),
        ],
    )
    year = StringField(
        "Year",
        default=str(datetime.datetime.today().year),
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: 2024"},
    )
    number = StringField(
        "Number",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: #1, #2"},
    )
    sensor_type = StringField(
        "Sensor Type",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: PM2.5, NO2, T, RH"},
    )
    source = StringField(
        "Source",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: Nanosampler (ug/m3), PCD, TMD"},
    )
    starting_date = DateField("Starting Date", format="%d-%m-%Y")
    stoping_date = DateField("Stoping Date", format="%d-%m-%Y")
    value = FloatField(
        "Value",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: 1.45"},
    )


class ClimateRecordFileForm(FlaskForm):
    upload_file = fields.FileField(
        "Upload file",
        validators=[
            FileAllowed(
                ["xlsx"],
                "Invalid file format. Please upload an Excel file (.xlsx) only.",
            )
        ],
    )
