from flask import request, jsonify, make_response
from flask_login import login_required
from sqlalchemy.exc import NoResultFound

from src.app import API, db
from src.app.models import Permission
from src.app.views.api import bp
from src.app.views.decorators import permission_required


DEFAULT_ECOSYSTEMS = "recent"


@bp.app_errorhandler(403)
def api_forbidden(error):
    return make_response(jsonify({"error": "Access forbidden"}), 403)


@bp.app_errorhandler(500)
def API_internal_error(error):
    db.session.rollback()
    return make_response(jsonify({"error": "Internal error"}), 500)

# REM: errors 404 and 405 are handled in a different way, directly in errors.handlers


@bp.route("/app/functionalities", methods=["GET"])
def get_app_functionalities():
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems="recent")
    ecosystems_info = API.ecosystems.get_ecosystems_management(
        session=db.session, ecosystems_query_obj=ecosystem_qo)
    functionalities = API.ecosystems.summarize_ecosystems_management(
        session=db.session, ecosystems_info=ecosystems_info)
    return jsonify(functionalities)


@bp.route("/weather/sun_times", methods=["GET"])
def get_sun_times():
    response = API.weather.get_suntimes_data()
    return jsonify(response)


@bp.route("/system/current_data", methods=["GET"])
@login_required  # TODO: use jwt token
@permission_required(Permission.ADMIN)
def get_current_system_data():
    response = API.admin.get_current_system_data()
    return jsonify(response)


@bp.route("/system/data", methods=["GET"])
@login_required  # TODO: use jwt token
@permission_required(Permission.ADMIN)
def get_system_data():
    historic_system_data = API.admin.get_historic_system_data(db.session)
    return jsonify(historic_system_data)


@bp.route("/ecosystems/status", methods=["GET"])
def get_ecosystems_status():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems)
    response = API.ecosystems.get_ecosystems(
        session=db.session, ecosystems_query_obj=ecosystem_qo)
    return jsonify(response)


@bp.route("/ecosystems/management", methods=["GET"])
def get_management():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems)
    response = API.ecosystems.get_ecosystems_management(
        session=db.session, ecosystems_query_obj=ecosystem_qo)
    return jsonify(response)


@bp.route("/ecosystems/sensors_skeleton", methods=["GET"])
def get_sensors_skeleton():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    level = request.args.get("level", "all")
    # TODO: think about time later
    start_time = request.args.get("start_time", None)
    end_time = request.args.get("end_time", None)
    time_window = API.utils.create_time_window(start_time, end_time)
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems
    )
    response = API.ecosystems.get_ecosystems_sensors_data_skeleton(
        session=db.session, ecosystems_query_obj=ecosystem_qo,
        time_window=time_window, level=level
    )
    return jsonify(response)


@bp.route("/ecosystems/sensors", methods=["GET"])
def get_sensors():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    scope = request.args.get("scope", "current")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems)
    if scope == "current":
        response = API.ecosystems.get_current_sensors_data(
            session=db.session, ecosystems_query_obj=ecosystem_qo
        )
    elif scope == "historic":
        response = "To be done"
    else:
        response = "Choose scope from 'current' or 'historic'"
    return jsonify(response)


@bp.route("/ecosystems/sensors/<sensor_uid>", methods=["GET"])
def get_sensor_by_uid(sensor_uid: str):
    start_time = request.args.get("start_time", None)
    end_time = request.args.get("end_time", None)
    time_window = API.utils.create_time_window(start_time, end_time)
    response = API.ecosystems.get_historic_sensors_data_by_sensor(
        session=db.session, sensor_uid=sensor_uid, measures="all",
        time_window=time_window,
    )
    return jsonify(response)


@bp.route("/ecosystems/sensors/<sensor_uid>", methods=["POST"])
def create_sensor_by_uid(sensor_uid: str):
    pass  # TODO


@bp.route("/ecosystems/sensors/<sensor_uid>/<measure>", methods=["GET"])
def get_sensor(sensor_uid: str, measure: str = None):
    start_time = request.args.get("start_time", None)
    end_time = request.args.get("end_time", None)
    time_window = API.utils.create_time_window(start_time, end_time)
    response = API.ecosystems.get_historic_sensor_data(
        session=db.session, sensor_uid=sensor_uid, measure=measure,
        time_window=time_window,
    )
    return jsonify({
        "measure": measure, "sensor_uid": sensor_uid, "values": response
    })


@bp.route("/ecosystems/hardware", methods=["GET"])
def get_hardware():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    level = request.args.get("level", "all").split(",")
    hardware_type = request.args.get("hardware_type", "all").split(",")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems
    )
    response = API.ecosystems.get_hardware(
        session=db.session, ecosystems_query_obj=ecosystem_qo, level=level,
        hardware_type=hardware_type
    )
    return jsonify(response)


@bp.route("/ecosystems/hardware/<uid>", methods=["GET"])
def get_hardware_by_uid(uid: str):
    response = API.ecosystems.get_hardware_by_uid(
        session=db.session, hardware_uid=uid)
    return jsonify(response)


@bp.route("/ecosystems/hardware/<uid>",  methods=["POST"])
@login_required  # TODO: use flask auth
@permission_required(Permission.OPERATE)
def create_hardware_by_uid(uid: str):
    pass  # TODO


@bp.route("/ecosystems/hardware/<int:uid>",  methods=["DELETE"])
@login_required  # TODO: use flask auth
@permission_required(Permission.OPERATE)
def del_hardware_by_uid(uid: str):
    pass  # TODO


@bp.route("/ecosystems/light", methods=["GET"])
def light_data():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems
    )
    response = API.ecosystems.get_light_info(ecosystem_qo)
    return jsonify(response)


@bp.route("/test", methods=["GET"])
def test():
    ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
    return jsonify(ecosystems)
