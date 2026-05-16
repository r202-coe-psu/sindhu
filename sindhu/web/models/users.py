from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, data):
        self.data = data

    def __getattr__(self, attr):
        return self.data[attr]

    def has_roles(self, role) -> bool:
        roles = self.data.get("roles", [])
        return role in roles

    def get_picture(self) -> str | None:
        return None
