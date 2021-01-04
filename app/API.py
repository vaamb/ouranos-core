from datetime import datetime, time, timedelta, timezone
from statistics import mean, StatisticsError, mode

from app.services import weather
from app.database import out_of_Flask_data_db as db
from app.dataspace import Outside, sensorsData
from app.models import sensorData, Hardware, Ecosystem, Light


summary_sep = "\n=================================\n"
ecosystem_summary_sep = "---------------------------------\n"


"""
Ecosystem related calls
"""
measure_unit = {"absolute_humidity": "g/m³",
                "dew_point": "°C",
                "temperature": "°C",
                "humidity": "% hum",
                "light": " lux",
                "moisture": " RWC"}


def get_connected_ecosystems():
    return [ecosystem for ecosystem in sensorsData]


def get_ecosystem_uid(ecosystem_name):
    with db.scoped_session() as session:
        ecosystem_id = (session.query(Ecosystem)
                        .filter_by(name=ecosystem_name)
                        .first().id)
    return ecosystem_id


def get_listed_ecosystems(ecosystem_names=[]):
    found = []
    not_found = []
    if not ecosystem_names:
        found = get_connected_ecosystems()
    else:
        for ecosystem_name in ecosystem_names:
            try:
                found += [get_ecosystem_uid(ecosystem_name)]
            except AttributeError:
                not_found += [ecosystem_name]
    return {"found": found, "not_found": not_found}


class ecosystems:
    def get_ecosystem_light_info(ecosystem_uid, translate_uid=False):
        with db.scoped_session() as session:
            light = session.query(Light).filter_by(ecosystem_id=ecosystem_uid).first()
            mode = light.mode
            status = light.status
        if translate_uid:
            with db.scoped_session() as session:
                uid = session.query(Ecosystem).filter_by(id=ecosystem_uid).first().name
        else:
            uid = ecosystem_uid
        return {uid: {"mode": mode, "status": status}}

    @staticmethod
    def get_ecosystem_current_data(ecosystem_uid, translate_uid=False):
        data = sensorsData[ecosystem_uid]  # call it first so have the same error for all case
        if translate_uid:
            with db.scoped_session() as session:
                uid = session.query(Ecosystem).filter_by(id=ecosystem_uid).first().name
        else:
            uid = ecosystem_uid
        return {uid: data}


def summarize_ecosystem_current_data(current_ecosystem_data):
    ecosystem_uid = list(current_ecosystem_data.keys())[0]
    data = current_ecosystem_data[ecosystem_uid]["data"]
    values = {}
    for sensor in data:
        for measure in data[sensor]:
            try:
                values[measure].append(data[sensor][measure])
            except KeyError:
                values[measure] = [data[sensor][measure]]
    for measure in values:
        values[measure] = round(mean(values[measure]), 2)
    return {ecosystem_uid: values}


def get_ecosystem_measures_mean(db_session,
                                ecosystem_uid,
                                level,
                                time_window=("start", "now")):
    time_window_a = (time_window[0] if time_window[0] != "start"
                     else datetime.fromtimestamp(0))
    time_window_p = (time_window[1] if time_window[1] != "now"
                     else datetime.now())
    result = {}

    measures = [d.measure for d in
                (db_session.query(sensorData).join(Hardware)
                 .filter(sensorData.ecosystem_id == ecosystem_uid)
                 .filter(Hardware.level == level)
                 .filter(time_window_a < sensorData.datetime)
                 .filter(sensorData.datetime <= time_window_p)
                 .group_by(sensorData.measure)
                 .all())]

    for measure in measures:
        result[measure] = {}
        _data = (db_session.query(sensorData).join(Hardware)
                 .filter(sensorData.ecosystem_id == ecosystem_uid)
                 .filter(Hardware.level == level)
                 .filter(sensorData.measure == measure)
                 .filter(time_window_a < sensorData.datetime)
                 .filter(sensorData.datetime <= time_window_p)
                 .with_entities(sensorData.datetime, sensorData.value)
                 .all())
        data = round(mean([i[1] for i in _data]), 2)
        result[measure] = data
    return result


def get_environments_summary(time_window):
    measures_summary = {}
    with db.scoped_session() as session:
        ecosystem_ids = (session.query(Ecosystem)
                         .filter_by(status=1)
                         .with_entities(Ecosystem.id, Ecosystem.name)
                         .all())
        for ecosystem_id in ecosystem_ids:
            summary = (get_ecosystem_measures_mean(db_session=session,
                                                   ecosystem_uid=ecosystem_id[0],
                                                   level="environment",
                                                   time_window=time_window))
            if summary:
                measures_summary[ecosystem_id[1]] = summary
    return measures_summary


"""
Weather-related calls
"""
def get_current_weather():
    weather_data = weather.get_data()
    weather_short = {
        "temperature": weather_data["currently"]["temperature"],
        "humidity": weather_data["currently"]["humidity"],
        "windSpeed": weather_data["currently"]["windSpeed"],
        "cloudCover": weather_data["currently"]["cloudCover"],
        "precipProbability": weather_data["currently"][
            "precipProbability"],
        "summary": weather_data["currently"]["summary"],
    }
    return weather_short


def format_current_weather(current_weather):
    return f"Currently, the weather is {current_weather['summary'].lower()}. " +\
           f"It is {current_weather['temperature']}°C and the relative " +\
           f"humidity is of {current_weather['humidity']*100}%. " +\
           f"The wind speed is of {current_weather['windSpeed']} km/h and " \
           f"the cloud coverage is of {current_weather['cloudCover']*100}%"


def get_time_of_day(_time):
    if _time < time(7, 0):
        return "night"
    elif time(7, 0) <= _time <= time(12, 0):
        return "morning"
    elif time(12, 0) < _time <= time(18, 30):
        return "afternoon"
    elif time(18, 30) < _time:
        return "evening"


def get_weather_forecast(time_window=24):
    weather_data = weather.get_data()
    data = []
    for hour in range(time_window):
        data.append(weather_data["hourly"][hour])
    return data


weather_measures = {"mean": ["temperature", "humidity", "windSpeed", 
                             "cloudCover", "precipProbability"],
                    "mode": ["summary"]}


def digest_weather_forecast(weather_forecast):
    now = datetime.now(timezone.utc)
    today = {}
    tomorrow = {}
    for hour in weather_forecast:
        data = hour
        dt = datetime.fromtimestamp(data["time"])
        tod = get_time_of_day(dt.time())
        if dt.date() == now.date():
            day = today
        elif dt.date() == now.date() + timedelta(days=1):
            day = tomorrow

        try:
            day[tod]
        except KeyError:
            day[tod] = {}

        for info in weather_measures["mean"] + weather_measures["mode"]:
            try:
                day[tod][info].append(data[info])
            except KeyError:
                day[tod].update({info: [data[info]]})

    return {"today": today, "tomorrow": tomorrow}


def summarize_weather_forecast(digested_weather_forecast):
    for day in digested_weather_forecast:
        global_summary = []
        for tod in digested_weather_forecast[day]:
            for info in weather_measures["mean"]:
                try:
                    digested_weather_forecast[day][tod][info] =\
                        round(mean(digested_weather_forecast[day][tod][info]), 1)
                except StatisticsError:
                    digested_weather_forecast[day][tod][info] = None
            for info in weather_measures["mode"]:
                try:
                    if info == "summary":
                        global_summary += digested_weather_forecast[day][tod][info]
                    digested_weather_forecast[day][tod][info] =\
                        mode(digested_weather_forecast[day][tod][info])
                except StatisticsError:
                    digested_weather_forecast[day][tod][info] = None
        try:
            digested_weather_forecast[day]["global_summary"] = mode(global_summary)
        except StatisticsError:  # if no mode (for ex: 2 with same number of values)
            pass
    return digested_weather_forecast


# TODO: digest warnings
def digest_warnings():
    return {}


def format_ecosystem_recap(summarized_measures, base=""):
    if not summarized_measures:
        return ""
    ecosystems_summary = base
    for i, ecosystem in enumerate(summarized_measures):
        indent = (len(ecosystem)) * " "
        for j, measure in enumerate(summarized_measures[ecosystem]):
            unit = measure_unit.get(measure, "")
            if j == 0:
                left = ecosystem
            else:
                left = indent
            ecosystems_summary += \
                (f"{left} - {measure}: ".replace("_", " ") +
                 f"{summarized_measures[ecosystem][measure]}{unit}\n")
        if i < len(summarized_measures) - 1:
            ecosystems_summary += ecosystem_summary_sep
    return ecosystems_summary[:-1]


# TODO: make in general, currently only works with modified summary
def format_weather_forecast(summarized_weather, days=("today", "tomorrow")):
    message = ""
    for day in days:
        before = False
        message += f"{day.capitalize()}'s weather will be "
        for moment in ["night", "morning", "afternoon", "evening"]:
            try:
                summarized_weather[day][moment]
                if before:
                    message += ", "
                message += f"{summarized_weather[day][moment]['temperature']}°C " +\
                           f"in the {moment}"
                before = True
            except KeyError:
                pass
        message += ". "
        try:
            message += f"It will be {summarized_weather[day]['global_summary'].lower()}. "
        except KeyError:
            pass
    return message


# TODO format warnings message
def format_warnings_recap(digested_warnings):
    if not digested_warnings:
        return f"Great, you have no warnings."


class Messages:
    @staticmethod
    def ecosystem_current(ecosystem_names=[]):
        ecosystems = get_listed_ecosystems(ecosystem_names=ecosystem_names)
        message = ""
        end_message = ""
        summarized_data = {}
        for ecosystem_uid in ecosystems["found"]:
            data = ecosystems.get_ecosystem_current_data(ecosystem_uid, translate_uid=True)
            summarized_data.update(summarize_ecosystem_current_data(data))
        if summarized_data:
            if len(summarized_data) > 1:
                s = "s"
            else:
                s = ""
            message += f"Here are the current sensors data for your ecosystem{s}:\n"
            message += format_ecosystem_recap(summarized_data, base="")
        if ecosystems["not_found"]:

            for ecosystem in ecosystems["not_found"]:
                message += f"There is no ecosystem named {ecosystem}."
            message += f"\n{end_message}"
        return message

    @staticmethod
    def recap(start=(datetime.now()-timedelta(days=1)),
              stop=datetime.now(),
              ecosystem_message_base="Last 24h sensors average:\n"):
        today = datetime.now().strftime("%A %d %B")
        # get environmental summary for yesterday
        measures_summary = get_environments_summary(
            time_window=(start, stop))
        formatted_ecosystem_recap = format_ecosystem_recap(measures_summary,
                                                           base=ecosystem_message_base)
        # get weather forecast
        weather_forecast = get_weather_forecast(26)
        digested_weather_forecast = digest_weather_forecast(weather_forecast)
        summarized_weather_forecast = summarize_weather_forecast(digested_weather_forecast)
        formatted_weather_forecast = format_weather_forecast(summarized_weather_forecast)
        # get warning messages
        digested_warnings = digest_warnings()
        formatted_warnings_recap = format_warnings_recap(digested_warnings)
        # get important calendar message
        calendar_message = "Don't forget to water and feed your plants."
        # put all messages together
        message = f"GAIA daily recap for {today}{summary_sep}"
        for formatted_message in [formatted_ecosystem_recap,
                                  formatted_weather_forecast,
                                  formatted_warnings_recap,
                                  calendar_message]:
            if formatted_message:
                message += formatted_message
                message += summary_sep
        message += "Have a nice day!"
        return message

    @staticmethod
    def weather(when="current", **kwargs):
        assert when in ["current", "forecast"]
        if when == "current":
            current_weather = get_current_weather()
            return format_current_weather(current_weather)
        else:
            time_window = kwargs.get("time_window", 24)
            weather_forecast = get_weather_forecast(time_window=time_window)
            digested_weather = digest_weather_forecast(weather_forecast)
            summarized_weather = summarize_weather_forecast(digested_weather)
            return format_weather_forecast(summarized_weather)
