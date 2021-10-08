from datetime import datetime, timezone

import cachetools.func
from flask import abort, current_app, flash, redirect, render_template, \
    request, url_for
from flask_login import current_user, login_required
from flask_sqlalchemy import get_debug_queries

from src.app import API, db
from src.app.API.ecosystems import ecosystemIds
from src.models import HealthData, Service, User, Permission
from src.app.views import layout
from src.app.views.main import bp
from src.app.views.main.forms import EditProfileForm
from src.app.wiki import get_wiki


wiki_engine = get_wiki()


def get_ecosystem_ids_or_404(ecosystem: str) -> ecosystemIds:
    try:
        return API.ecosystems.get_ecosystem_ids(session=db.session,
                                                ecosystem=ecosystem)
    except API.exceptions.NoEcosystemFound:
        abort(404)


@bp.after_app_request
def after_request(response):
    for query in get_debug_queries():
        if query.duration >= current_app.config["SLOW_DB_QUERY_TIME"]:
            current_app.logger.warning(f"Slow query: {query.statement}\n" +
                                       f"Parameters: {query.parameters}\n" +
                                       f"Duration: {query.duration}\n" +
                                       f"Context: {query.context}\n")
    return response


@bp.after_app_request
def update_user_last_seen(response):
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc).replace(microsecond=0)
        db.session.commit()
    return response


@bp.app_context_processor
@cachetools.func.ttl_cache(ttl=60)
def menu_info():
    ecosystems_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems="recent")
    ecosystems_management = API.ecosystems.get_ecosystems_management(
        session=db.session, ecosystems_query_obj=ecosystems_qo)
    summarized_ecosystems_management = API.ecosystems.summarize_ecosystems_management(
        session=db.session, ecosystems_info=ecosystems_management)
    dropdowns = API.app.get_functionalities(
        summarized_ecosystems_management, db.session
    )
    plant_articles = [article for article
                      in sorted(wiki_engine.articles_available(("plants_care",))["plants_care"])]
    plant_articles.insert(0, plant_articles.pop(plant_articles.index("general")))

    anyWarnings = API.warnings.check_any_recent_warnings(db.session)

    return {
        "Permission": Permission,
        "dropdowns": dropdowns,
        "plant_articles": plant_articles,
        "anyWarnings": anyWarnings,
    }


@bp.route("/")
def to_home():
    return redirect(url_for("main.home"))


@bp.route("/home")
def home():
    sun_times = API.weather.get_suntimes_data()
    current_weather = API.weather.get_current_weather()
    current_system_data = API.admin.get_current_system_data()
    if current_user.is_authenticated:
        warnings = API.warnings.get_recent_warnings(db.session, limit=8)
    else:
        warnings = []
    return render_template("main/home.html", title="Home",
                           sun_times=sun_times,
                           current_weather=current_weather,
                           current_system_data=current_system_data,
                           warnings=warnings,
                           parameters=layout.parameters,
                           )


@bp.route("/weather")
def weather():
    "weather" in API.app.get_services_running(db.session) or abort(404)
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
    ecosystem_ids = get_ecosystem_ids_or_404(ecosystem=ecosystem_name)
    recent_ecosystems = API.ecosystems.get_recent_ecosystems(
        session=db.session, time_limit=API.utils.time_limits()["sensors"]
    )
    if ecosystem_ids.uid not in recent_ecosystems:
        abort(404)
    title = f"{ecosystem_ids[1]} {level} data"

    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystem_name,
    )
    time_window = API.utils.create_time_window()

    sensors_skeleton = API.ecosystems.get_ecosystems_sensors_data_skeleton(
        session=db.session, ecosystems_query_obj=ecosystem_qo,
        time_window=time_window, level=level
    )

    current_sensors_data = API.ecosystems.get_current_sensors_data(
            session=db.session, ecosystems_query_obj=ecosystem_qo
    )

    graphUpdatePeriod = current_app.config["SENSORS_LOGGING_PERIOD"]
    return render_template("main/sensors.html", title=title,
                           sensors_skeleton=sensors_skeleton,
                           ecosystem_ids=ecosystem_ids,
                           level=level,
                           current_sensors_data=current_sensors_data,
                           graphUpdatePeriod=graphUpdatePeriod,
                           parameters=layout.parameters,
                           )


@bp.route("/health")
@bp.route("/health/<ecosystem_name>")
def health(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids_or_404(ecosystem=ecosystem_name)
    recent_ecosystems = API.ecosystems.get_recent_ecosystems(
        session=db.session, time_limit=API.utils.time_limits()["health"]
    )
    if ecosystem_ids.uid not in recent_ecosystems:
        abort(404)

    data = (HealthData.query.filter(HealthData.ecosystem_id == ecosystem_ids[0])
            .filter(
        HealthData.datetime >= API.utils.time_limits()["health"])
            .with_entities(HealthData.datetime, HealthData.health_index, HealthData.green,
                           HealthData.necrosis)
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
    ecosystem_ids = get_ecosystem_ids_or_404(ecosystem=ecosystem_name)
    connected_ecosystems = API.ecosystems.get_connected_ecosystems(db.session)
    if ecosystem_ids.uid not in connected_ecosystems:
        abort(404)
    title = f"{ecosystem_ids[1]} switches control"
    ecosystems_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystem_name
    )
    light_data = API.ecosystems.get_light_info(ecosystems_qo)
    return render_template("main/switches.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           switches={
                               "light": light_data[0],
                           },
                           )


@bp.route("/warnings")
@login_required
def warnings():
    warnings = API.warnings.get_recent_warnings(db.session)
    return render_template("main/warning.html", title="Warnings",
                           warnings=warnings
                           )


@bp.route("/about")
def about():
    return render_template("main/about.html", title="About")


@bp.route("/license")
def _license():
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


@bp.route("/settings/<ecosystem_name>")
@login_required
def settings(ecosystem_name: str):
    ecosystem_ids = get_ecosystem_ids_or_404(ecosystem=ecosystem_name)
    title = f"{ecosystem_ids[1]} settings"
    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
        session=db.session, ecosystems=ecosystem_name
    )
    ecosystem = API.ecosystems.get_ecosystems(
        session=db.session, ecosystems_query_obj=ecosystem_qo
    )
    managements = API.ecosystems.get_ecosystems_management(
        session=db.session, ecosystems_query_obj=ecosystem_qo
    )
    light = API.ecosystems.get_light_info(ecosystem_qo)
    environmental_param = API.ecosystems.get_environmental_parameters(
        session=db.session, ecosystems_query_obj=ecosystem_qo
    )
    hardware = API.ecosystems.get_hardware(
        session=db.session, ecosystems_query_obj=ecosystem_qo
    )
    plants = API.ecosystems.get_plants(
        session=db.session, ecosystems_query_obj=ecosystem_qo
    )
    return render_template("main/settings.html", title=title,
                           ecosystem_ids=ecosystem_ids,
                           ecosystem=ecosystem,
                           managements=managements,
                           light=light,
                           environmental_param=environmental_param,
                           hardware=hardware,
                           plants=plants,
                           )


@bp.route("/settings/engine_managers")
@login_required
def engine_managers():
    managers_qo = API.ecosystems.get_managers_query_obj(session=db.session)
    managers = API.ecosystems.get_managers(session=db.session,
                                           managers_qo=managers_qo)
    return render_template("main/managers.html", managers=managers)
