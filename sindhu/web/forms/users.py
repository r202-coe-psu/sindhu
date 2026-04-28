from wtforms import validators
from wtforms import fields

from flask_wtf import FlaskForm


class LoginForm(FlaskForm):
    username = fields.StringField(
        "Username", validators=[validators.InputRequired(), validators.Length(min=3)]
    )
    password = fields.PasswordField(
        "Password", validators=[validators.InputRequired(), validators.Length(min=3)]
    )


class UserForm(FlaskForm):
    username = fields.StringField(
        "Username", validators=[validators.InputRequired(), validators.Length(min=3)]
    )
    first_name = fields.StringField(
        "First Name", validators=[validators.InputRequired(), validators.Length(min=3)]
    )
    last_name = fields.StringField(
        "Last Name", validators=[validators.InputRequired(), validators.Length(min=3)]
    )
    email = fields.EmailField(
        "Email", validators=[validators.InputRequired(), validators.Length(min=3)]
    )

    password = fields.PasswordField(
        "Password",
        validators=[
            validators.InputRequired(),
            validators.Length(min=3),
            validators.EqualTo("confirm_password", message="Passwords must match"),
        ],
    )
    confirm_password = fields.PasswordField(
        "Confirm Password",
        validators=[validators.InputRequired(), validators.Length(min=3)],
    )


class SearchUserForm(FlaskForm):
    username = fields.StringField("Username")
    email = fields.EmailField("Email")
