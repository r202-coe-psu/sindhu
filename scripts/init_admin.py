import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sindhu import models


async def create_user_admin():
    class Setting:
        def __init__(self):
            self.MONGODB_URI = "mongodb://localhost/sindhudb"

    settings = Setting()
    if len(sys.argv) > 1:
        settings.MONGODB_URI = "mongodb://mongodb/sindhudb"

    await models.init_beanie(None, settings)

    print("start check admin")
    user = await models.users.User.find_one(models.users.User.username == "admin")

    if user:
        print("Found admin user", user)
        return
    print("end check admin")

    print("start create admin")
    user = models.users.User(
        email="admin@example.com",
        username="admin",
        first_name="admin",
        last_name="system",
        password="",
        roles=["user", "admin"],
        status="active",
    )
    user.set_password("p@ssw0rd")
    await user.save()
    print("finish")


if __name__ == "__main__":
    asyncio.run(create_user_admin())
