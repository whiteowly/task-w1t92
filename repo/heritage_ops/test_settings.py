import os

from heritage_ops.settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE", "heritage_ops"),
        "USER": os.getenv("MYSQL_USER", "heritage"),
        "PASSWORD": env_or_file("MYSQL_PASSWORD", default=""),
        "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "TEST": {
            "NAME": os.getenv("MYSQL_TEST_DATABASE", "test_heritage_ops"),
        },
    }
}
