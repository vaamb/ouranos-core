from flask import request, jsonify
from flask_restx import Namespace, Resource

from src.app import API, db


namespace = Namespace(
    "app",
    description="Base information for the app interface.",
)
