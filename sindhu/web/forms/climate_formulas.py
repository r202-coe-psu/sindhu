import datetime
from wtforms import (
    validators,
    StringField,
    FloatField,
    ValidationError,
    IntegerField,
    SelectField,
    DateField,
)
from flask_wtf import FlaskForm

from sindhu import models


class ClimateFormulaForm(FlaskForm):
    name = StringField(
        "Formula Name",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "Formula Name"},
    )
    formula = StringField(
        "Formula",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: \\sqrt{25 - x^2}"},
    )
    formula_unit = StringField(
        "Unit",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: Unit"},
    )
    sensor_type = StringField(
        "Sensor Type",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: PM0.1, PM2.5"},
    )
    sensor_type_result = StringField(
        "Sensor Type Result",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: PM0.1, PM2.5,"},
    )
    source = StringField(
        "Source",
        validators=[validators.InputRequired()],
        render_kw={"placeholder": "ex: PCD, TMD"},
    )
    status = SelectField(
        "Status",
        default="active",
        choices=[
            ("active", "active"),
            ("disactive", "disactive"),
        ],
    )


def get_climate_formula_variable_form(
    # variables, climate_formula=None, sensor_type=None
    variables,
    climate_formula=None,
):

    class ClimateFormulaVariableForm(FlaskForm):
        pass

    default = {"PM_2_5": "PM_2_5"}
    if climate_formula.variables:
        default = climate_formula.variables.to_dict()

    sensor_tpye = models.config.CLIMATE_FORMULA_SENSORS

    print(sensor_tpye)

    for var in variables:
        var = str(var)
        setattr(
            ClimateFormulaVariableForm,
            var,
            SelectField(
                "Variable",
                default=default.get(var, 0),
                choices=[(key, choice) for key, choice in sensor_tpye.items()],
            ),
        )

    return ClimateFormulaVariableForm()


class ClimateFormulaSearchForm(FlaskForm):
    name = StringField("Name")
    source = StringField("Source")
    sensor_type = StringField("Thai Name")
    status = SelectField(
        "Status",
        default="active",
        choices=[
            ("active", "active"),
            ("disactive", "disactive"),
        ],
    )
