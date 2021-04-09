from flask import Blueprint

bp = Blueprint('errors', __name__)

from app.views.errors import handlers
