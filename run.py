import os

from flask import Flask

from app.routes import register_routes
from app.utils.data.database import get_database_path


app = Flask(__name__, template_folder="app/templates")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or None,
    DATABASE_PATH=str(get_database_path()),
    DEBUG=os.environ.get("FLASK_DEBUG", "0").lower() in {"1", "true"},
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("SESSION_COOKIE_SECURE", "0").lower() in {"1", "true"}
    ),
)
register_routes(app)

if __name__ == '__main__':
    app.run()
