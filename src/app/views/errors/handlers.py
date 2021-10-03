from flask import jsonify, render_template, request

from src.app import db
from src.app.views.errors import bp


@bp.app_errorhandler(401)
def forbidden(e):
    return render_template('errors/401.html', title="Error 401",
                           description=e.description), 401


@bp.app_errorhandler(404)
def page_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Not found"}), 404
    return render_template('errors/404.html', title="Error 404"), 404


@bp.app_errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Method not allowed"}), 405
    return render_template('errors/404.html', title="Error 404"), 404


@bp.app_errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('errors/500.html', title="Error 500"), 500
