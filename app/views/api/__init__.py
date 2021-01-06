from flask import Blueprint

bp = Blueprint('api', __name__)

from app.views.api import routes
