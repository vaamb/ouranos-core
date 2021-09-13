from flask import Blueprint

bp = Blueprint("main", __name__)

from src.app.views.main import routes
