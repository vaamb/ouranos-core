from fastapi import Depends, HTTPException, status

from . import router
from src import api
from src.app.auth import is_operator
from src.app.dependencies import get_session


def ecosystems_or_abort(session, ecosystems):
    ecosystems_qo = api.gaia.get_ecosystems(
        session=session, ecosystems=ecosystems
    )
    if ecosystems_qo:
        return ecosystems_qo
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Ecosystem(s) not found"
    )


@router.get("/ecosystem")
async def get_ecosystems(uid: list = ["all"], session=Depends(get_session)):
    ecosystems = ecosystems_or_abort(uid)
    response = [api.gaia.get_ecosystem_info(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.post("/ecosystem/u", dependencies=[Depends(is_operator)])
async def post_ecosystem(session=Depends(get_session)):
    pass


@router.get("/ecosystem/u/<uid>")
async def get_ecosystem(uid: str, session=Depends(get_session)):
    def exception():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Engine not found"}
        )
    if "all" in uid or len(uid.split(",")) > 1:
        exception()
    ecosystem = ecosystems_or_abort(session, uid)
    response = api.gaia.get_ecosystem_info(session, ecosystem[0])
    return response


@router.put("/ecosystem/u/<uid>", dependencies=[Depends(is_operator)])
async def put_ecosystem(uid: str, session=Depends(get_session)):
        pass


@router.delete("/ecosystem/u/<uid>", dependencies=[Depends(is_operator)])
async def delete_ecosystem(uid: str, session=Depends(get_session)):
    pass


@router.get("/ecosystem/management")
async def get_managements(uid: list = ["all"], session=Depends(get_session)):
    ecosystems = ecosystems_or_abort(session, uid)
    response = [api.gaia.get_ecosystem_management(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@namespace.route("/ecosystem/u/<uid>/management")
class ManagementU(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/management to get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_ecosystem_management(
                db.session, ecosystem[0]
            )
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404


@namespace.route("/ecosystem/sensors_skeleton")
class SensorsSkeleton(Resource):
    @namespace.doc(params={
        **ecosystem_param, **level_param, **time_window_params,
    })
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        level = request.args.get("level", "all")
        time_window = get_time_window_from_request_args()
        response = [api.gaia.get_ecosystem_sensors_data_skeleton(
            db.session, ecosystem, time_window, level
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/sensors_skeleton")
class SensorsSkeletonS(Resource):
    @namespace.doc(params={
        **no_default(ecosystem_param), **level_param, **time_window_params
    })
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/sensors_skeleton to "
                                 "get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        level = request.args.get("level", "all")
        time_window = get_time_window_from_request_args()
        if ecosystem:
            response = api.gaia.get_ecosystem_sensors_data_skeleton(
                db.session, ecosystem[0], time_window, level
            )
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404


@namespace.route("/ecosystem/light")
class Light(Resource):
    @namespace.doc(params={**ecosystem_param})
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        response = [api.gaia.get_light_info(
            db.session, ecosystem
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/light")
class LightU(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/light to get more "
                                 "than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_light_info(db.session, ecosystem[0])
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404


@namespace.route("/ecosystem/environment_parameters")
class EnvironmentParameters(Resource):
    @namespace.doc(params={**ecosystem_param})
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        response = [api.gaia.get_environmental_parameters(
            db.session, ecosystem
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/environment_parameters")
class EnvironmentParametersU(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/environment_parameters "
                                 "to get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_environmental_parameters(
                db.session, ecosystem[0]
            )
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404
