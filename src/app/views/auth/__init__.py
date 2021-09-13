from flask import Blueprint

bp = Blueprint("auth", __name__)

from src.app.views.auth import routes
