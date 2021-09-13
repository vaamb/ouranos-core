from flask import request, jsonify
from flask_login import login_required
from sqlalchemy.exc import NoResultFound

from src.app import API, db
from src.app.models import Permission
from src.app.views.api import bp
from src.app.views.decorators import permission_required


def make_api_response(f):
    def decorator(*args, **kwargs):
        try:
            return jsonify({
                "status": 200,
                "results": f(*args, **kwargs),
            })
        except NoResultFound:
            return jsonify({
                "status": 404,
                "results": None,
            })
    return decorator


@bp.route("/app/functionalities", methods=["GET"])
#@make_api_response
def app_functionalities():
    ecosystem_qo = API.ecosystems.get_recent_ecosystems_query_obj(
        session=db.session)
    ecosystems_info = API.ecosystems.get_ecosystems_info(
        session=db.session, ecosystems_query_obj=ecosystem_qo)
    functionalities = API.ecosystems.summarize_ecosystems_info(
        session=db.session, ecosystems_info=ecosystems_info)
    return jsonify(functionalities)


@bp.route("/app/sun_times", methods=["GET"])
#@make_api_response
def sun_times():
    response = API.weather.get_suntimes_data()
    return jsonify(response)


@bp.route("/hardware/delete/<int:uid>")
@login_required
@permission_required(Permission.OPERATE)
def delete_hardware(uid):
    pass


@bp.route("/system/current_data", methods=["GET"])
@login_required
@permission_required(Permission.ADMIN)
#@make_api_response
def current_system_data():
    response = API.admin.get_current_system_data()
    return jsonify(response)


@bp.route("/ecosystems/info", methods=["GET"])
#@make_api_response
def ecosystem_info():
    ecosystems = request.args.get("ecosystems", "all")
    if ecosystems[0] == "recent":
        ecosystem_qo = API.ecosystems.get_recent_ecosystems_query_obj(
            session=db.session)
    elif ecosystems[0] == "connected":
        ecosystem_qo = API.ecosystems.get_connected_ecosystems_query_obj(
            session=db.session)
    else:
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems)
    response = API.ecosystems.get_ecosystems_info(
        session=db.session, ecosystems_query_obj=ecosystem_qo)
    return jsonify(response)


@bp.route("/ecosystems/sensors_skeleton", methods=["GET"])
#@make_api_response
def sensors_skeleton():
    ecosystems = request.args.get("ecosystems", "all")
    level = request.args.get("level", "all")
    # TODO: think about time later
    start_time = request.args.get("start_time", None)
    end_time = request.args.get("end_time", None)
    time_window = API.utils.create_time_window(start_time, end_time)
    qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems
    )
    response = API.ecosystems.get_ecosystems_sensors_data_skeleton(
        session=db.session, ecosystems_query_obj=qo, time_window=time_window,
        level=level
    )
    return jsonify(response)


@bp.route("/ecosystems/sensor/<sensor_id>/<measure>", methods=["GET"])
#@make_api_response
def sensor(sensor_id: str, measure: str = None):
    start_time = request.args.get("start_time", None)
    end_time = request.args.get("end_time", None)
    time_window = API.utils.create_time_window(start_time, end_time)
    response = API.ecosystems.get_historic_sensor_data(
        session=db.session, sensor_id=sensor_id, measure=measure,
        time_window=time_window,
    )
    return jsonify(response)


@bp.route("/ecosystems/hardware", methods=["GET"])
#@make_api_response
def hardware():
    ecosystems = request.args.get("ecosystems", "all")
    level = request.args.get("level", "all")
    hardware_type = request.args.get("hardware_type", "all")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems
    )
    response = API.ecosystems.get_hardware(
        session=db.session, ecosystems_qo=ecosystem_qo, level=level,
        hardware_type=hardware_type
    )
    return jsonify(response)


@bp.route("/ecosystems/light_data", methods=["GET"])
#@make_api_response
def light_data():
    ecosystems = request.args.get("ecosystems", "all")
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystems
    )
    response = API.ecosystems.get_light_info(ecosystem_qo)
    return jsonify(response)
