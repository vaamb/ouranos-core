from flask import Blueprint

bp = Blueprint("errors", __name__)

from src.app.views.errors import handlers
