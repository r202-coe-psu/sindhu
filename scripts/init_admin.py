import sys
import os
from dotenv import load_dotenv
from sindhu import models
import asyncio

load_dotenv()


async def create_user_admin(password):
    class Setting:
        def __init__(self):
            self.MONGODB_URI = os.getenv(
                "MONGODB_URI", "mongodb://localhost:27017/sindhudb"
            )

    settings = Setting()

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
    user.set_password(password)
    await user.save()
    print("finish")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: poetry run python {sys.argv[0]} <password>")
        sys.exit(1)

    password = sys.argv[1]
    asyncio.run(create_user_admin(password))
