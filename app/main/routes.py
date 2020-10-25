from datetime import date, datetime, timedelta
import time

from flask import render_template, url_for, redirect, abort
from flask_login import login_required, current_user

from app import db
from app.models import User, Ecosystem, Hardware, Data, Health
from app.dataspace import sensorsData, Outside
from app.main import bp, layout
from app.wiki import simpleWiki


warnings = {}


def get_ecosystem_ids(ecosystem_name):
    ecosystem_ids = (Ecosystem.query.filter_by(name=ecosystem_name)
                                    .with_entities(Ecosystem.id, Ecosystem.name).first())  # or 404
    return ecosystem_ids


def get_sensors_data(level, ecosystem_uid, days=7):
    time_limit = datetime.utcnow()-timedelta(days=days)
    data = {}
    measures = [d.measure for d in
                Data.query.join(Hardware)
                          .filter(Data.ecosystem_id == ecosystem_uid).filter(Hardware.level == level)
                          .filter(Data.datetime >= time_limit)
                          .group_by(Data.measure).all()]
    for measure in measures:
        data[measure] = {}
        sensors_id = [d.sensor_id for d in
                      Data.query.join(Hardware)
                                .filter(Data.ecosystem_id == ecosystem_uid).filter(Hardware.level == level)
                                .filter(Data.measure == measure)
                                .group_by(Data.sensor_id).all()]
        for sensor_id in sensors_id:
            sensor_name = Hardware.query.filter_by(id=sensor_id).first().name
            _data = (Data.query.join(Hardware)
                               .filter(Data.ecosystem_id == ecosystem_uid).filter(Hardware.level == level)
                               .filter(Data.measure == measure).filter(Data.sensor_id == sensor_id)
                               .filter(Data.datetime >= time_limit)
                               .with_entities(Data.datetime, Data.value).all())
            data[measure][sensor_id] = {"name": sensor_name,
                                        "values": _data}
    return data


@bp.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
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
    logged_ecosystems = Ecosystem.query.all()
    ecosystems = {e.id:
                      {"name": e.name,
                       "status": e.status,
                       "webcam": True if e.webcam in ["regular", "NoIR"] else False,
                       "lighting": e.lighting,
                       "health": e.health,
                       "env_sensors": True if e.hardware.filter_by(type="sensor", level="environment").first() else False,
                       "plant_sensors": True if e.hardware.filter_by(type="sensor", level="plants").first() else False,
                       "lights": True if e.hardware.filter_by(type="light").first() else False,
                       "switches": e.id in sensorsData
                       }
                  for e in logged_ecosystems
                  }
    # list comprehension before passing to jinja
    dropdowns = {"webcam": True if True in [ecosystems[ecosystem]["webcam"] for ecosystem in ecosystems] else False,
                 "lighting": True if True in [ecosystems[ecosystem]["lighting"] for ecosystem in ecosystems] else False,
                 "health": True if True in [ecosystems[ecosystem]["health"] for ecosystem in ecosystems] else False,
                 "env_sensors": True if True in [ecosystems[ecosystem]["env_sensors"]
                                                 for ecosystem in ecosystems] else False,
                 "plant_sensors": True if True in [ecosystems[ecosystem]["plant_sensors"]
                                                   for ecosystem in ecosystems] else False,
                 "switches": True if True in [ecosystems[ecosystem]["switches"] for ecosystem in ecosystems] else False,
                 }
    return {"dropdowns": dropdowns,
            "ecosystems": ecosystems,
            "plants_in_wiki": [],
            }


@bp.route("/")
def to_home():
    return redirect(url_for("main.home"))


@bp.route("/home")
def home():
    def parse_moment(moment):
        _time = datetime.strptime(moment, "%I:%M:%S %p").time()
        return datetime.combine(date.today(), _time)
    logged_ecosystems = Ecosystem.query.all()
    light_data = {e.id: {"status": e.light.one().status,
                         "mode": e.light.one().mode,
                         "method": e.light.one().method,
                         "morning_start": e.light.one().morning_start,
                         "morning_end": e.light.one().morning_end,
                         "evening_start" :e.light.one().evening_start,
                         "evening_end": e.light.one().evening_end,
                         }
                  for e in logged_ecosystems}
    moments = {"sunrise": parse_moment(Outside.moments_data["sunrise"]),
               "sunset": parse_moment(Outside.moments_data["sunset"]),
               }
    return render_template("main/home.html", title="Home",
                           weather_data=Outside.weather_data,
                           light_data=light_data,
                           today=time.time(),
                           moments=moments,
                           )


@bp.route("/weather")
def weather():
    return render_template("main/weather.html", title="Weather",
                           home_city="Arlon",
                           weather_data=Outside.weather_data,
                           )


@bp.route("/sensors/<level>/<ecosystem_name>")
def sensors(level, ecosystem_name):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    data = get_sensors_data(ecosystem_uid=ecosystem_ids[0], level=level, days=7)
    last_data = sensorsData.get(ecosystem_ids[0], {})
    title = f"{ecosystem_ids[1]} {level} data"
    return render_template("main/sensors.html", title=title,
                           ecosystem_ids=ecosystem_ids, level=level,
                           data=data, last_data=last_data,
                           parameters=layout.parameters,
                           )


@bp.route("/health")
@bp.route("/health/<ecosystem_name>")
def health(ecosystem_name):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    data = (Health.query.filter(Health.ecosystem_id == ecosystem_ids[0])
                        .filter(Health.datetime >= (datetime.utcnow()-timedelta(days=31)))
                        .with_entities(Health.datetime, Health.health_index, Health.green, Health.necrosis)).all()
    title = "{} plants health".format(ecosystem_ids[1])
    return render_template("main/health.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           data=data,
                           parameters=layout.parameters,
                           )


@bp.route("/switches")
@bp.route("/switches/<ecosystem_name>")
def switches(ecosystem_name):
    if not ecosystem_name:
        abort(404)
    ecosystem_ids = (Ecosystem.query.filter_by(name=ecosystem_name).
                     with_entities(Ecosystem.id, Ecosystem.name).one())
    title = "{} switches control".format(ecosystem_ids[1])
    return render_template("main/switches.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           )


@bp.route("/settings")
@bp.route("/settings/<ecosystem_name>")
def settings(ecosystem_name):
    ecosystem_ids = get_ecosystem_ids(ecosystem_name=ecosystem_name)
    title = "{} settings".format(ecosystem_ids[1])
    return render_template("main/settings.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           )


@bp.route("/care")
@bp.route("/care/<species>")
@login_required
def care(species="general"):
    title = f"{species.capitalize()} care"
    return render_template("main/care.html", title=title,
                           metadata=simpleWiki().get_article("plants_care", species, data="metadata"),
                           content=simpleWiki().get_article("plants_care", species),
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
def user_page(username):
    user = User.query.filter_by(username=username).first()  # or 404
    posts = [
        {'author': user, 'body': 'Test post #1'},
        {'author': user, 'body': 'Test post #2'}
    ]
    #    if user == current_user:
    return render_template('main/user.html', title="User {}".format(username),
                           user=user, posts=posts)
