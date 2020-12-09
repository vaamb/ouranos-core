from datetime import date, datetime, time, timedelta, timezone
import platform

from flask import abort, current_app, redirect, render_template, url_for
from flask_login import current_user, login_required
from flask_sqlalchemy import get_debug_queries

from app import db
from app.dataspace import Outside, sensorsData
from app.main import bp, layout
from app.models import sensorData, Ecosystem, Hardware, Health, User
from app.wiki import simpleWiki
from config import Config


warnings = {}


# define time limits
def time_limits() -> dict:
    now_utc = datetime.now(timezone.utc)
    return {
        "ecosystems": (now_utc - timedelta(hours=36)),
        "sensors": (now_utc - timedelta(days=2)).replace(tzinfo=None),
        "health": (now_utc - timedelta(days=7)).replace(tzinfo=None),
        "status": (now_utc - timedelta(minutes=5)).replace(tzinfo=None)
    }


def recent_ecosystems():
    time_limit = (datetime.now(timezone.utc) - timedelta(hours=36))
    return Ecosystem.query \
                    .filter(Ecosystem.last_seen >= time_limit) \
                    .all()


def time_to_datetime(t: time) -> datetime:
    if isinstance(t, time):
        t = datetime.combine(date.today(), t)
    return t


def on_off(value: bool) -> str:
    if value:
        return "on"
    return "off"


def get_ecosystem_ids(ecosystem_name: str) -> str:
    # TODO: add the "or 404"
    ecosystem_ids = (Ecosystem.query.filter_by(name=ecosystem_name)
                     .with_entities(Ecosystem.id,
                                    Ecosystem.name).first())  # or 404
    return ecosystem_ids


# TODO: try to optimize this 
# Maybe need to add a measure model?
def get_sensors_data(level: str, ecosystem_uid: str, days: int = 7):
    time_limit = datetime.utcnow() - timedelta(days=days)
    data = {}
    measures = [d.measure for d in
                sensorData.query.join(Hardware)
                    .filter(sensorData.ecosystem_id == ecosystem_uid)
                    .filter(Hardware.level == level)
                    .filter(sensorData.datetime >= time_limit)
                    .group_by(sensorData.measure).all()]
    for measure in measures:
        data[measure] = {}
        sensors_id = [d.sensor_id for d in
                      sensorData.query.join(Hardware)
                          .filter(sensorData.ecosystem_id == ecosystem_uid)
                          .filter(Hardware.level == level)
                          .filter(sensorData.measure == measure)
                          .group_by(sensorData.sensor_id).all()]
        for sensor_id in sensors_id:
            sensor_name = Hardware.query.filter_by(id=sensor_id).first().name
            _data = (sensorData.query.join(Hardware)
                     .filter(sensorData.ecosystem_id == ecosystem_uid)
                     .filter(Hardware.level == level)
                     .filter(sensorData.measure == measure)
                     .filter(sensorData.sensor_id == sensor_id)
                     .filter(sensorData.datetime >= time_limit)
                     .with_entities(sensorData.datetime, sensorData.value).all())
            data[measure][sensor_id] = {"name": sensor_name,
                                        "values": _data}
    return data


@bp.after_app_request
def after_request(response):
    for query in get_debug_queries():
        if query.duration >= current_app.config["SLOW_DB_QUERY_TIME"]:
            current_app.logger.warning(f"Slow query: {query.statement}\n" +
                                       f"Parameters: {query.parameters}\n" +
                                       f"Duration: {query.duration}\n" +
                                       f"Context: {query.context}\n")
    return response


@bp.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()


@bp.app_context_processor
def inject_warning():
    warning = False
    if current_user.is_authenticated:
        if warnings:
            warning = True
    return {"warning": warning}


@bp.app_context_processor
def menu_info():
    limits = time_limits()

    ecosystems = {
        e.id: {
            "name": e.name,
            "status": on_off(e.status) if e.last_seen >= limits["status"] else "disconnected",
            "webcam": True if e.webcam in ["regular", "NoIR"] else False,
            "lighting": e.lighting,
            "health": True if (
                Health.query.filter_by(ecosystem_id=e.id)
                            .filter(Health.datetime >= limits["health"])
                            .first()) else False,
            "env_sensors": True if (
                Hardware.query.filter_by(ecosystem_id=e.id)
                        .filter_by(type="sensor", level="environment")
                        .filter(Hardware.last_log >= limits["sensors"])
                        .first()) else False,
            "plant_sensors": True if (
                Hardware.query.filter_by(ecosystem_id=e.id)
                        .filter_by(type="sensor", level="plants")
                        .filter(Hardware.last_log >= limits["sensors"])
                        .first()) else False,
            "lights": True if e.hardware.filter_by(type="light").first() else False,
            "switches": e.id in sensorsData
        }
        for e in recent_ecosystems()
    }

    # list comprehension for menu dropdown before passing to jinja
    dropdowns = {
        "webcam": True if True in [ecosystems[ecosystem]["webcam"]
                                   for ecosystem in ecosystems] else False,
        "lighting": True if True in [ecosystems[ecosystem]["lighting"]
                                     for ecosystem in ecosystems] else False,
        "health": True if True in [ecosystems[ecosystem]["health"]
                                   for ecosystem in ecosystems] else False,
        "env_sensors": True if True in [ecosystems[ecosystem]["env_sensors"]
                                        for ecosystem in
                                        ecosystems] else False,
        "plant_sensors": True if True in [
            ecosystems[ecosystem]["plant_sensors"]
            for ecosystem in ecosystems] else False,
        "switches": True if True in [ecosystems[ecosystem]["switches"]
                                     for ecosystem in ecosystems] else False,
    }

    return {"ecosystems": ecosystems,
            "dropdowns": dropdowns,
            "plants_in_wiki": [],
            }


@bp.route("/")
def to_home():
    return redirect(url_for("main.home"))


@bp.route("/home")
def home():
    def parse_moment(moment: str) -> datetime:
        _time = datetime.strptime(moment, "%I:%M:%S %p").time()
        return datetime.combine(date.today(), _time)

    light_data = {
        e.id: {
            "status": e.light.one().status,
            "mode": e.light.one().mode,
            "method": e.light.one().method,
            "morning_start": time_to_datetime(e.light.one().morning_start),
            "morning_end": time_to_datetime(e.light.one().morning_end),
            "evening_start": time_to_datetime(e.light.one().evening_start),
            "evening_end": time_to_datetime(e.light.one().evening_end),
        }
        for e in recent_ecosystems()
    }

    moments = {
        "sunrise": parse_moment(Outside.moments_data["sunrise"]),
        "sunset": parse_moment(Outside.moments_data["sunset"]),
    }

    return render_template("main/home.html", title="Home",
                           weather_data=Outside.weather_data,
                           light_data=light_data,
                           today=date.today(),
                           moments=moments,
                           platform=platform.system(),
                           )


@bp.route("/weather")
def weather():
    return render_template("main/weather.html", title="Weather",
                           home_city=Config.HOME_CITY,
                           weather_data=Outside.weather_data,
                           )


@bp.route("/sensors/<level>/<ecosystem_name>")
def sensors(level: str, ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    data = get_sensors_data(ecosystem_uid=ecosystem_ids[0], level=level,
                            days=7)
    last_data = sensorsData.get(ecosystem_ids[0], {})
    title = f"{ecosystem_ids[1]} {level} data"
    return render_template("main/sensors.html", title=title,
                           ecosystem_ids=ecosystem_ids, level=level,
                           data=data, last_data=last_data,
                           parameters=layout.parameters,
                           )


@bp.route("/health")
@bp.route("/health/<ecosystem_name>")
def health(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    data = (Health.query.filter(Health.ecosystem_id == ecosystem_ids[0])
            .filter(
        Health.datetime >= (datetime.utcnow() - timedelta(days=31)))
            .with_entities(Health.datetime, Health.health_index, Health.green,
                           Health.necrosis)
            .all())
    title = f"{ecosystem_ids[1]} plants health"
    return render_template("main/health.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           data=data,
                           parameters=layout.parameters,
                           )


@bp.route("/switches")
@bp.route("/switches/<ecosystem_name>")
def switches(ecosystem_name: str):
    if not ecosystem_name:
        abort(404)
    ecosystem_ids = (Ecosystem.query.filter_by(name=ecosystem_name)
                              .with_entities(Ecosystem.id, Ecosystem.name)
                              .one())
    if ecosystem_ids[0] not in sensorsData:
        abort(404)
    title = f"{ecosystem_ids[1]} switches control"
    return render_template("main/switches.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           )


@bp.route("/settings")
@bp.route("/settings/<ecosystem_name>")
def settings(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    title = f"{ecosystem_ids[1]} settings"
    return render_template("main/settings.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           )


@bp.route("/care")
@bp.route("/care/<species>")
@login_required
def care(species: str = "general"):
    title = f"{species.capitalize()} care"
    return render_template("main/care.html", title=title,
                           metadata=simpleWiki().get_article("plants_care",
                                                             species,
                                                             data="metadata"),
                           content=simpleWiki().get_article("plants_care",
                                                            species),
                           )


@bp.route("/warnings")
@login_required
def warnings_list():
    return render_template("main/warning.html", title="Warnings",
                           warnings=warnings
                           )


@bp.route("/about")
def about():
    return render_template("main/about.html", title="About")


@bp.route("/license")
def license():
    return render_template("main/license.html")


@bp.route("/preferences")
@login_required
def preferences():
    return render_template("main/preferences.html", title="GAIA preferences")


@bp.route("/faq")
def faq():
    return render_template("main/faq.html", title="F.A.Q.")


@bp.route('/user/<username>')
@login_required
def user_page(username: str):
    user = User.query.filter_by(username=username).first_or_404()  # or 404
    posts = [
        {'author': user, 'body': 'Test post #1'},
        {'author': user, 'body': 'Test post #2'}
    ]
    if user == current_user:
        return render_template('main/user_me.html', title=f"User {username}",
                               user=user, posts=posts)
    return render_template('main/user.html', title="User {}".format(username),
                           user=user, posts=posts)
