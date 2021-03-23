from datetime import date, datetime, time, timedelta, timezone
import platform

import cachetools.func
from flask import abort, current_app, flash, redirect, render_template, \
    request, url_for
from flask_login import current_user, login_required
from flask_sqlalchemy import get_debug_queries

from app import db
from app.dataspace import sensorsData
from app.models import sensorData, Ecosystem, Hardware, Health, Service, User, \
    Management, Warning
from app.services import services_manager
from app.views.main import bp, layout
from app.views.main.forms import EditProfileForm
from app.utils import parse_sun_times
from app.wiki import simpleWiki
from config import Config


warnings = {}


weather_service = services_manager.services["weather"]
sun_times_service = services_manager.services["sun_times"]
system_monitor = services_manager.services["system_monitor"]


def time_limits() -> dict:
    now_utc = datetime.now(timezone.utc)
    return {
        "ecosystems": (now_utc - timedelta(hours=36)),
        "sensors": (now_utc - timedelta(days=2)).replace(tzinfo=None),
        "health": (now_utc - timedelta(days=7)).replace(tzinfo=None),
        "status": (now_utc - timedelta(seconds=Config.ECOSYSTEM_TIMEOUT)
                   ).replace(tzinfo=None)
    }


@cachetools.func.ttl_cache(ttl=60)
def get_recent_warnings():
    time_limit = (datetime.now(timezone.utc) - timedelta(days=7))
    return (Warning.query.filter(Warning.datetime >= time_limit)
                         .filter(Warning.solved == False)
                         .order_by(Warning.level.desc())
                         .order_by(Warning.row_id)
                         .all()
            )


def recent_ecosystems():
    time_limit = (datetime.now(timezone.utc) - timedelta(hours=36))
    return Ecosystem.query \
                    .filter(Ecosystem.last_seen >= time_limit) \
                    .all()


def time_to_datetime(t: time) -> datetime:
    if isinstance(t, time):
        t = datetime.combine(date.today(), t, tzinfo=timezone.utc)
    return t


def on_off(value: bool) -> str:
    if value:
        return "on"
    return "off"


def get_ecosystem_ids(ecosystem_name: str) -> str:
    ecosystem_ids = (Ecosystem.query.filter_by(name=ecosystem_name)
                     .with_entities(Ecosystem.id,
                                    Ecosystem.name).first_or_404())
    return ecosystem_ids


# TODO: try to optimize this
# TODO: don't use ecosystem_uid but rather Ecosystem query result
# Or cache?
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


def get_light_data(ecosystem_query):
    return {
        e.id: {
            "status": e.light.one().status,
            "mode": e.light.one().mode,
            "method": e.light.one().method,
            "morning_start": time_to_datetime(e.light.one().morning_start),
            "morning_end": time_to_datetime(e.light.one().morning_end),
            "evening_start": time_to_datetime(e.light.one().evening_start),
            "evening_end": time_to_datetime(e.light.one().evening_end),
        } for e in ecosystem_query
    }


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
        current_user.last_seen = datetime.now(timezone.utc).replace(microsecond=0)
        db.session.commit()


@bp.app_context_processor
@cachetools.func.ttl_cache(ttl=60)
def menu_info():
    limits = time_limits()
    # TODO: move to API
    ecosystems = {
        e.id: {
            "name": e.name,
            "status": on_off(e.status) if e.last_seen >= limits["status"] else "disconnected",
            "webcam": e.manages(Management["webcam"]),
            "lighting": e.manages(Management["light"]),
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
            "switches": True if e.hardware.filter_by(type="light").first()
                            and e.manages(Management["light"])
                            and e.id in sensorsData else False,
        }
        for e in recent_ecosystems()
    }

    # list comprehension for menu dropdown before passing to jinja
    dropdowns = {
        "weather": True if weather_service.get_data() else False,
        "webcam": True if (True in [ecosystems[ecosystem]["webcam"]
                                    for ecosystem in ecosystems] and
                           "webcam" in [s.name
                                        for s in Service.query
                                                        .filter_by(status=1)
                                                        .all()]
                           ) else False,
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

    plants = []

    warnings = []

    if current_user.is_authenticated:
        warnings = get_recent_warnings()

    return {"ecosystems": ecosystems,
            "dropdowns": dropdowns,
            "plants_in_wiki": plants,
            "warnings": warnings,
            }


@bp.route("/")
def to_home():
    return redirect(url_for("main.home"))


@bp.route("/home")
def home():
    light_data = get_light_data(recent_ecosystems())

    sun_times = {}
    try:
        up = {
            "sunrise": parse_sun_times(
                sun_times_service.get_data()["sunrise"]),
            "sunset": parse_sun_times(
                sun_times_service.get_data()["sunset"]),
        }
        sun_times.update(up)
    except Exception as e:
        print(e)

    return render_template("main/home.html", title="Home",
                           weather_data=weather_service.get_data(),
                           light_data=light_data,
                           sun_times=sun_times,
                           platform=platform.system(),
                           system_data=system_monitor.system_data,
                           )


@bp.route("/weather")
def weather():
    weather_data = weather_service.get_data()
    if not weather_data:
        abort(404)
    return render_template("main/weather.html", title="Weather",
                           home_city=Config.HOME_CITY,
                           weather_data=weather_data,
                           )


@bp.route("/sensors/<level>/<ecosystem_name>")
def sensors(level: str, ecosystem_name: str):
    # TODO: send the sensor model info
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    data = get_sensors_data(ecosystem_uid=ecosystem_ids[0], level=level,
                            days=7)
    current_data = sensorsData
    title = f"{ecosystem_ids[1]} {level} data"
    return render_template("main/sensors.html", title=title,
                           ecosystem_ids=ecosystem_ids, level=level,
                           data=data, current_data=current_data,
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
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)

    if ecosystem_ids[0] not in sensorsData:
        abort(404)
    title = f"{ecosystem_ids[1]} switches control"

    e = Ecosystem.query.filter(Ecosystem.name == ecosystem_name)\
                       .one()
    light_data = get_light_data((e, ))

    return render_template("main/switches.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           light_data=light_data,
                           )


@bp.route("/settings")
@bp.route("/settings/<ecosystem_name>")
def settings(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    title = f"{ecosystem_ids[1]} settings"

    # TODO: first generate a ecosystem query, then use it
    environmental_sensors = (
        Hardware.query.filter_by(ecosystem_id=ecosystem_ids[0])
                      .filter_by(type="sensor")
                      .filter_by(level="environment")
                      .all()
    )
    plants_sensors = (
        Hardware.query.filter_by(ecosystem_id=ecosystem_ids[0])
                      .filter_by(type="sensor")
                      .filter_by(level="plants")
                      .all()
    )
    actuators = (
        Hardware.query.filter_by(ecosystem_id=ecosystem_ids[0])
                      .filter(Hardware.type != "sensor")
                      .filter_by(level="environment")
                      .all()
    )

    return render_template("main/settings.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           environmental_sensors=environmental_sensors,
                           plants_sensors=plants_sensors,
                           actuators=actuators,
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
                           warnings=get_recent_warnings()
                           )


@bp.route("/about")
def about():
    return render_template("main/about.html", title="About")


@bp.route("/license")
def the_license():
    return render_template("main/license.html")


@bp.route("/preferences")
@login_required
def preferences():
    return render_template("main/preferences.html", title="GAIA preferences")


@bp.route("/faq")
def faq():
    return render_template("main/faq.html", title="F.A.Q.")


@bp.route("/user/<username>", methods=["GET", "POST"])
@login_required
def user_page(username: str = None):
    user = User.query.filter_by(username=username).first_or_404()

    if user == current_user:
        services = Service.query.filter_by(status=1, level="user").all()
        form = EditProfileForm()
        if form.validate_on_submit():
            current_user.firstname = form.firstname.data
            current_user.lastname = form.lastname.data
            current_user.username = form.username.data
            current_user.email = form.email.data
            current_user.daily_recap = form.daily_recap.data
            current_user.daily_recap_channel_id = form.daily_recap_channels.data
            current_user.telegram = form.telegram.data
            current_user.telegram_chat_id = form.telegram_chat_id.data
            db.session.commit()
            flash('Your changes have been saved.')
            return redirect(url_for('main.user_page', username=current_user.username))

        elif request.method == "GET":
            form.firstname.data = current_user.firstname
            form.lastname.data = current_user.lastname
            form.username.data = current_user.username
            form.email.data = current_user.email
            form.daily_recap.data = current_user.daily_recap
            form.daily_recap_channels.data = current_user.daily_recap_channel_id
            form.telegram.data = current_user.telegram
            form.telegram_chat_id.data = current_user.telegram_chat_id
        return render_template('main/user_me.html', title=f"User {user.username}",
                               user=user, services=services, form=form)

    posts = [
        {'author': user, 'body': 'Test post #1'},
        {'author': user, 'body': 'Test post #2'}
    ]
    return render_template('main/user.html', title=f"User {user.username}",
                           user=user, posts=posts)
