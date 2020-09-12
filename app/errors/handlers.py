from flask import render_template

from app.errors import bp
from app import db_session

"""
app.logger.info(f"Page not found: {request.url}")
"""

@bp.app_errorhandler(403)
def page_not_found(e):
    return render_template('errors/403.html', title="Error 403",
                           description = e.description), 403

@bp.app_errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html', title="Error 404"), 404

@bp.app_errorhandler(500)
def internal_error(e):
    db_session.rollback()
    return render_template('errors/500.html', title="Error 500"), 500
