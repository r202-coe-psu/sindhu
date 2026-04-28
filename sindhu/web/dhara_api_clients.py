from dhara_client import Client, AuthenticatedClient
from flask import session
import datetime
from werkzeug.exceptions import Unauthorized


class DharaClient:
    def __init__(self):
        self.app = None

    def init_app(self, app):
        self.app = app

        base_url = app.config.get("DHARA_API_PRIVATE_BASE_URL")

        if not base_url:
            base_url = app.config.get("DHARA_API_BASE_URL")
        self.base_url = base_url
        self.verify_ssl = app.config.get("DHARA_API_VERIFY_SSL", False)

    def get_current_client(self, timeout=30, is_anonymous=False):
        tokens = session.get("tokens")
        expires_at = None
        if not tokens:

            if is_anonymous:
                return Client(
                    base_url=self.base_url, verify_ssl=self.verify_ssl, timeout=timeout
                )
            else:
                raise Unauthorized()

        expires_at = tokens.get("expires_at")
        if type(expires_at) == str:
            expires_at = datetime.datetime.fromisoformat(tokens.get("expires_at"))
        else:
            expires_at = datetime.datetime.fromisoformat(
                tokens.get("expires_at").strftime("%Y-%m-%dT%H:%M:%S")
            )

        now = datetime.datetime.now()

        if now + datetime.timedelta(minutes=10) < expires_at:
            token = tokens.get("access_token")
            return AuthenticatedClient(
                base_url=self.base_url,
                token=token,
                verify_ssl=self.verify_ssl,
                timeout=timeout,
            )

        raise Unauthorized()


def init_client(app):
    client.init_app(app)


client = DharaClient()
