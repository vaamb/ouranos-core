from datetime import datetime
import pytz
import platform

from flask import render_template, url_for, redirect, request, abort
from flask_login import login_required, current_user

from app import db2
from app.database import db_session
from app.models import Permission, Role, User
from app.wiki import simpleWiki
from app.main import bp, layout, aggregates
from app.main.decorators import permission_required

#from app.main.filters import human_delta_time


@bp.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db_session.commit()

@bp.route("/")
def to_home():
    return redirect(url_for("main.home"))

@bp.route("/home")
def home():
    return render_template("main/home.html", title="Home",
                           weather_data = aggregates.weather_data,
#                           uptime = human_delta_time(aggregates.start_time, 
#                                                     datetime.now().astimezone(pytz.timezone(aggregates.timezone))),
                           time_of_day = aggregates.get_time_of_day(),
                           health = aggregates.health_data,
                           light_hours = aggregates.get_light_hours(),
                           light_mode = aggregates.get_light_mode(),
                           light_status = aggregates.get_light_status(),
                           plants = aggregates.plants,
                           average = aggregates.get_environments_average(),
                           platform = platform.system(),
                           )

@bp.route("/weather")
def weather():
   return render_template("main/weather.html", title="Weather",
                           weather_data = aggregates.weather_data,
                           )

@bp.route("/environment")
@bp.route("/environment/<ecosystem_name>")
def environment(ecosystem_name = aggregates.tag_to_name[aggregates.ecosystems_with_environment_sensors[0]]):
    ecosystem = aggregates.name_to_tag[ecosystem_name]
    title = "{} environmental data".format(ecosystem_name)
    return render_template("main/environment.html", 
                           ecosystem = ecosystem, title=title,
                           ecosystem_name = ecosystem_name,
                           address_to_name = aggregates.address_to_name,
                           week_data = db2.get_data(ecosystem, "environment", 7),
                           parameters = layout.parameters,
                           )

@bp.route("/plants")
@bp.route("/plants/<ecosystem_name>")
def plants(ecosystem_name = aggregates.tag_to_name[aggregates.ecosystems_with_environment_sensors[0]]):
    ecosystem = aggregates.name_to_tag[ecosystem_name]
    title = "{} plants data".format(ecosystem_name)
    return render_template("main/plants.html", title=title,
                           ecosystem = ecosystem,
                           ecosystem_name = ecosystem_name,
                           address_to_name = aggregates.address_to_name,
                           week_data = db2.get_data(ecosystem, "plant", 7),
                           parameters = layout.parameters,
                           )

@bp.route("/health")
@bp.route("/health/<ecosystem_name>")
def health(ecosystem_name = aggregates.tag_to_name[aggregates.ecosystems_with_webcam[0]]):
    ecosystem = aggregates.name_to_tag[ecosystem_name]
    title = "{} plants health".format(ecosystem_name)
    return render_template("main/health.html", title=title,
                           ecosystem_name = ecosystem_name,
                           data = db2.get_data(ecosystem, "plant_health", 30),
                           parameters = layout.parameters,
                           )

@bp.route("/switches")
@bp.route("/switches/<ecosystem_name>")
def switches(ecosystem_name = aggregates.tag_to_name[aggregates.ecosystems_with_webcam[0]]):
    ecosystem = aggregates.name_to_tag[ecosystem_name]
    title = "{} switches control".format(ecosystem_name)
    return render_template("main/switches.html", title=title,
                           ecosystem_name = ecosystem_name,
                           ecosystem = ecosystem,
                           )

@bp.route("/settings")
@bp.route("/settings/<ecosystem_name>")
def settings(ecosystem_name = aggregates.tag_to_name[aggregates.ecosystems_with_webcam[0]]):
    ecosystem = aggregates.name_to_tag[ecosystem_name]
    title = "{} settings".format(ecosystem_name)
    return render_template("main/settings.html", title=title,
                           ecosystem = ecosystem,
                           )

@bp.route("/care")
@bp.route("/care/<species>")
@login_required
def care(species = "general"):
    title="{} care".format(species.capitalize())
    return render_template("main/care.html", title=title,
                           metadata = simpleWiki().get_article("plants_care", species, data = "metadata"),
                           content = simpleWiki().get_article("plants_care", species),
                           )

@bp.route("/warning")
def warning():
   return render_template("main/warning.html", title="Warnings",
#                          order = aggregates.warnings_order(),
                          )

@bp.route("/about")
def about():
    return render_template("main/about.html", title="About")

@bp.route("/license")
def myLicense():
    return render_template("main/license.html")

@bp.route("/preferences")
def preferences():
    return render_template("main/preferences.html", title="GAIA preferences")

@bp.route("/faq")
def faq():
    return render_template("main/faq.html", title="F.A.Q.")

@bp.route("/manuals")
def manuals(manuals):
    return render_template("main/manuals.html",
                           )

@bp.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first()
    if user is None: #if using flask-sqlalchemy, just use the fction first_or_404()
        abort(404)
    posts = [
        {'author': user, 'body': 'Test post #1'},
        {'author': user, 'body': 'Test post #2'}
    ]
#    if user == current_user:
    return render_template('main/user.html', title="User {}".format(username),
                           user=user, posts=posts)