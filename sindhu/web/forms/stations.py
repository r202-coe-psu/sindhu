from wtforms import validators, StringField, SelectField, Form, FormField
from flask_wtf import FlaskForm
from .fields import GeoField


class ClimateRecordStationForm(FlaskForm):
    name = StringField("Name", validators=[validators.InputRequired()])
    name_th = StringField("Thai Name")
    code = StringField("Station Code")
    coordinates = GeoField(
        "Coordinates [Lon, Lat]",
        default=[0, 0],
        validators=[validators.InputRequired()],
    )


class StationSearchForm(FlaskForm):
    source = StringField("Source")
    name = StringField("Name")
    name_th = StringField("Thai Name")
    code = StringField("Station Code")
    status = SelectField(
        "Status",
        default="active",
        choices=[
            ("active", "active"),
            ("disactive", "disactive"),
            ("suspend", "suspend"),
        ],
    )


# class MetadataAir4thaiStationForm(Form):
#     area_th = StringField("Area in thai", validators=[validators.InputRequired()])
#     area = StringField("Area")
#     place_code = StringField("Place Code", validators=[validators.InputRequired()])
#     is_gas = SelectField(
#         "Is gas",
#         default=False,
#         choices=[
#             (True, "active"),
#             (False, False),
#         ],
#     )


# class MetadataAirportStationForm(Form):
#     iata = StringField("IATA", validators=[validators.InputRequired()])
#     country = StringField("Country", validators=[validators.InputRequired()])
#     continent = StringField("Continent", validators=[validators.InputRequired()])


class CreateUpdateStationForm(FlaskForm):
    name = StringField("Name", validators=[validators.InputRequired()])
    name_th = StringField("Thai Name")
    code = StringField("Station Code", validators=[validators.InputRequired()])
    coordinates = GeoField(
        "Coordinates [Lon, Lat]",
        default=[0, 0],
        validators=[validators.InputRequired()],
    )
    url = StringField("URL", validators=[validators.InputRequired()])
    source = StringField("Source", validators=[validators.InputRequired()])
    status = SelectField(
        "Status",
        default="active",
        choices=[
            ("active", "active"),
            ("disactive", "disactive"),
            ("suspend", "suspend"),
        ],
    )


class CreateUpdateAir4thaiStationForm(CreateUpdateStationForm):
    area_th = StringField("Area in thai")
    area = StringField("Area")
    place_code = StringField("Place Code")
    is_gas = SelectField(
        "Is gas",
        default=False,
        choices=[
            (True, True),
            (False, False),
        ],
    )
    # metadata = FormField(MetadataAir4thaiStationForm)


class CreateUpdateAirportStationForm(CreateUpdateStationForm):
    iata = StringField("IATA")
    country = StringField("Country", validators=[validators.InputRequired()])
    continent = StringField("Continent", validators=[validators.InputRequired()])
    # metadata = FormField(MetadataAirportStationForm)
