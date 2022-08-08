from flask import abort, request

from src import api


def get_time_window_from_request_args() -> api.utils.timeWindow:
    start_time = request.args.get("start_time", None)
    end_time = request.args.get("end_time", None)
    try:
        return api.utils.create_time_window(start_time, end_time)
    except ValueError:
        abort(
            422,
            {
                "error": "'start_time' and 'end_time' should be valid times in "
                         "iso format"
            }
        )