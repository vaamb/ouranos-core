from datetime import datetime, timezone

import cachetools.func
from flask import abort, current_app, flash, redirect, render_template, \
    request, url_for
from flask_login import current_user, login_required
from flask_sqlalchemy import get_debug_queries

from app import db
from app import API
from app.API.various import wiki
from app.dataspace import sensorsData, sensorsDataHistory
from app.models import Hardware, Health, Service, User, Permission
from app.views.main import bp, layout
from app.views.main.forms import EditProfileForm


def get_ecosystem_ids(ecosystem, time_limit=None) -> str:
    ids = API.ecosystems.get_ecosystem_ids(ecosystem=ecosystem,
                                           session=db.session,
                                           time_limit=time_limit)
    return ids or abort(404)


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
    ecosystems_qo = API.ecosystems.get_recent_ecosystems_query_obj(session=db.session)
    ecosystems_info = API.ecosystems.get_ecosystems_info(
        ecosystems_qo, session=db.session)
    summarized_ecosystems_info = API.ecosystems.summarize_ecosystems_info(
        ecosystems_info, session=db.session)
    dropdowns = API.app.get_functionalities(
        summarized_ecosystems_info)

    plant_articles = [article for article
                      in sorted(wiki.articles_available["plants_care"])]
    plant_articles.insert(0, plant_articles.pop(plant_articles.index("general")))

    warnings = []
    if current_user.is_authenticated:
        warnings = API.warnings.get_recent_warnings(db.session)

    return {
        "Permission": Permission,
        "ecosystems_info": ecosystems_info,
        "dropdowns": dropdowns,
        "plant_articles": plant_articles,
        "warnings": warnings,
    }


@bp.route("/")
def to_home():
    return redirect(url_for("main.home"))


@bp.route("/home")
def home():
    current_weather = API.weather.get_current_weather()
    sun_times = API.weather.get_suntimes_data()
    ecosystems_qo = API.ecosystems.get_recent_ecosystems_query_obj(session=db.session)
    light_data = API.ecosystems.get_light_info(ecosystems_qo)
    system_data = API.admin.get_current_system_data()
    return render_template("main/home.html", title="Home",
                           current_weather=current_weather,
                           light_data=light_data,
                           sun_times=sun_times,
                           system_data=system_data,
                           current_data={**sensorsData},
                           parameters=layout.parameters,
                           )


@bp.route("/weather")
def weather():
    "weather" in API.app.get_services_running() or abort(404)
    current_weather = API.weather.get_current_weather()
    hourly_weather = API.weather.get_hourly_weather_forecast()
    daily_weather = API.weather.get_daily_weather_forecast()
    return render_template("main/weather.html", title="Weather",
                           home_city=current_app.config.get("HOME_CITY"),
                           current_weather=current_weather,
                           hourly_weather=hourly_weather,
                           daily_weather=daily_weather,
                           )


@bp.route("/sensors/<level>/<ecosystem_name>")
def sensors(level: str, ecosystem_name: str):
    # TODO: send the sensor model info
    ecosystem_ids = get_ecosystem_ids(ecosystem=ecosystem_name,
                                      time_limit=API.utils.time_limits()[
                                          "sensors"]
                                      )

    ecosystem_qo = API.ecosystems.get_ecosystem_query_obj(
        ecosystem_name, session=db.session
    )
    historic_sensors_data = API.ecosystems.get_historic_sensors_data(
        ecosystem_qo, session=db.session, level=(level, ))
    current_sensors_data = sensorsData
    title = f"{ecosystem_ids[1]} {level} data"
    return render_template("main/sensors.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           level=level,
                           current_sensors_data=current_sensors_data,
                           historic_sensors_data=historic_sensors_data,
                           parameters=layout.parameters,
                           )


@bp.route("/health")
@bp.route("/health/<ecosystem_name>")
def health(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids(ecosystem=ecosystem_name,
                                      time_limit=API.utils.time_limits()[
                                          "health"]
                                      )
    data = (Health.query.filter(Health.ecosystem_id == ecosystem_ids[0])
            .filter(
        Health.datetime >= API.utils.time_limits()["health"])
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
    ecosystem_ids = get_ecosystem_ids(
        ecosystem=ecosystem_name, time_limit="connected")
    title = f"{ecosystem_ids[1]} switches control"
    ecosystems_qo = API.ecosystems.get_ecosystem_query_obj(session=db.session)
    light_data = API.ecosystems.get_light_info(ecosystems_qo)

    return render_template("main/switches.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           light_data=light_data,
                           )


@bp.route("/settings")
@bp.route("/settings/<ecosystem_name>")
def settings(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids(ecosystem=ecosystem_name)
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
    hardware_dict = {
        "Environmental sensors": environmental_sensors,
        "Plants sensors": plants_sensors,
        "Actuators": actuators,
    }
    return render_template("main/settings.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           hardware_dict=hardware_dict,
                           )


@bp.route("/care")
@bp.route("/care/<species>")
@login_required
def care(species: str = "general"):
    title = f"{species.capitalize()} care"
    article = wiki.get_article("plants_care", species)
    return render_template("main/care.html", title=title,
                           article=article,
                           )


@bp.route("/warnings")
@login_required
def warnings_list():
    warnings = API.warnings.get_recent_warnings(db.session)
    return render_template("main/warning.html", title="Warnings",
                           warnings=warnings
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
        # TODO: simply show form without the ability to change anything
        #  to change: fresh login and redirect to other page
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
