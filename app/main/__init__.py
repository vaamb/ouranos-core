from flask import Blueprint
bp = Blueprint('main', __name__)

from app.gaiaAggregator_old import gaiaAggregator
aggregates = gaiaAggregator()

from app.models import Permission
from app.main import routes, filters, events

@bp.app_context_processor
def inject_permissions():
    return dict(Permission=Permission)

@bp.app_context_processor
def is_connected():
    return dict(is_connected=aggregates.is_connected)

@bp.app_context_processor
def test_connection():
    return dict(Permission=Permission)

@bp.app_context_processor
def inject_warnings():
    return dict(warnings=aggregates.get_warnings())

@bp.app_context_processor
def inject_info():
    return {"machine_type": "raspi",
            "home_city": aggregates.home_city,
            "tag_to_name": aggregates.tag_to_name,
            "address_to_name": aggregates.address_to_name,
            "ecosystems": {"status": aggregates.get_ecosystems_status(),
                           "active": aggregates.active_ecosystems,
                           "with_environment_sensors": aggregates.ecosystems_with_environment_sensors,
                           "with_plant_sensors": aggregates.ecosystems_with_plant_sensors,
                           "with_webcam": aggregates.ecosystems_with_webcam,
                           "with_actuators": aggregates.ecosystems_with_actuators,
                           },
            "plants_in_wiki": sorted(aggregates.plant_specific_articles()),
            "last_data": aggregates.sensors_data,
            "system_data": aggregates.resources_data,
            #"user" : aggregates.user_firstname,
            }
