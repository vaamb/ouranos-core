from . import bp
#from src.app import jwtManager


@bp.app_errorhandler(404)
def handle_404(e):
    return {"error": "This resource does not exist. Consult '/api/doc' to see "
                     "available resources"}, 404


@bp.app_errorhandler(403)
def handle_404(e):
    return {"error": "You don't have the permission to access to this resource"}, 403

"""
@jwtManager.expired_token_loader
def expired_token(jwt_header, jwt_payload):
    return {"error": "This token has expired"}, 401


@jwtManager.token_verification_failed_loader
def invalid_verification_token(jwt_header, jwt_payload):
    return {"error": "This token cannot be verified. It might have been tampered"}, 401
"""
