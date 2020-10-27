from flask import render_template

from app.errors import bp


@bp.app_errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html', title="Error 403",
                           description = e.description), 403


@bp.app_errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html', title="Error 404"), 404


@bp.app_errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('errors/500.html', title="Error 500"), 500
