from app.API import weather


def get_functionalities(summarized_ecosystems_info):
    app_functionalities = summarized_ecosystems_info
    app_functionalities["weather"] = True if weather.is_on() else False
    return app_functionalities
