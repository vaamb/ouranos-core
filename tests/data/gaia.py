from __future__ import annotations

import uuid
from typing import NamedTuple

from datetime import datetime, time, timezone

import gaia_validators as gv


timestamp_now = datetime.now(timezone.utc)
ip_address = "127.0.0.1"
engine_sid = uuid.uuid4()
engine_uid = "engine_uid"
ecosystem_uid = "zutqsCKn"
ecosystem_name = "TestingEcosystem"
hardware_uid = "hardware_uid"
request_uuid = uuid.uuid4()


def wrap_ecosystem_data_payload(data: dict | list[dict] | NamedTuple) -> dict:
    return {
        "uid": ecosystem_uid,
        "data": data,
    }


ecosystem_dict = {
    "engine_uid": engine_uid,
    "uid": ecosystem_uid,
    "name": ecosystem_name,
    "status": False,
    "registration_date": timestamp_now,
    "last_seen": timestamp_now,
    "management": 0,
}


engine_dict = {
    "uid": engine_uid,
    "sid": engine_sid,
    "registration_date": (
        timestamp_now.replace(microsecond=0)
    ),
    "address": ip_address,
    "last_seen": timestamp_now,
}


base_info: gv.BaseInfoConfigDict = {
    "engine_uid": engine_uid,
    "uid": ecosystem_uid,
    "name": ecosystem_name,
    "status": True,
}


base_info_payload: gv.BaseInfoConfigPayloadDict = \
    wrap_ecosystem_data_payload(base_info)


management_data: gv.ManagementConfigDict = {
    "sensors": True,
    "light": True,
    "climate": True,
    "watering": False,
    "health": False,
    "database": False,
    "alarms": False,
    "pictures": False,
}


management_payload: gv.ManagementConfigPayloadDict = \
    wrap_ecosystem_data_payload(management_data)


chaos: gv.ChaosConfigDict = {
    "frequency": 10,
    "duration": 2,
    "intensity": 0.2,
}


sky: gv.SkyConfigDict = {
    "day": time(6, 0),
    "night": time(22, 0),
    "lighting": gv.LightMethod.elongate,
}


climate: gv.ClimateConfigDict = {
    "parameter": "temperature",
    "day": 42,
    "night": 21,
    "hysteresis": 5,
}


environmental_payload: gv.EnvironmentConfigPayloadDict = \
    wrap_ecosystem_data_payload(
        gv.EnvironmentConfig(
            chaos=chaos,
            sky=sky,
            climate=[climate]
        ).model_dump()
    )


hardware_data: gv.HardwareConfigDict = {
    "uid": hardware_uid,
    "name": "TestThermometer",
    "address": "GPIO_7",
    "type": gv.HardwareType.sensor.name,
    "level": gv.HardwareLevel.environment.name,
    "model": "virtualDHT22",
    "measures": ["temperature|°C"],
    "plants": [],
    "multiplexer_model": None,
}


hardware_payload: gv.HardwareConfigPayloadDict = \
    wrap_ecosystem_data_payload([hardware_data])


measure_record = gv.MeasureAverage(
    "temperature",
    42,
    None
)


sensor_record = gv.SensorRecord(
    hardware_uid,
    "temperature",
    42,
    None,
)


alarm_record = gv.SensorAlarm(
    sensor_uid=hardware_uid,
    measure="temperature",
    position=gv.Position.above,
    delta=20.0,
    level=gv.WarningLevel.critical,
)


sensors_data: gv.SensorsDataDict = {
    "timestamp": timestamp_now,
    "records": [sensor_record],
    "average": [measure_record],
    "alarms": [alarm_record],
}


sensors_data_payload: gv.SensorsDataPayloadDict = \
    wrap_ecosystem_data_payload(sensors_data)


health_data: gv.HealthRecord = gv.HealthRecord(
    green=0.57,
    necrosis=0.15,
    index=0.85,
    timestamp=timestamp_now,
)


health_data_payload: gv.HealthDataPayloadDict = \
    wrap_ecosystem_data_payload(health_data)


light_data: gv.LightDataDict = {
    "morning_start": timestamp_now.time(),
    "morning_end": timestamp_now.time(),
    "evening_start": timestamp_now.time(),
    "evening_end": timestamp_now.time(),
    "method": gv.LightMethod.elongate,
}


light_data_payload: gv.LightDataPayloadDict = \
    wrap_ecosystem_data_payload(light_data)


turn_actuator_payload: gv.TurnActuatorPayloadDict = {
    "ecosystem_uid": ecosystem_uid,
    "actuator": gv.HardwareType.light,
    "mode": gv.ActuatorModePayload.automatic,
    "countdown": 0.0,
}


gaia_warning = {
    "level": "low",
    "title": "Not a problem",
    "description": "Super low level warning",
    "created_on": timestamp_now,
}


buffered_data_humidity = gv.BufferedSensorRecord(
    ecosystem_uid=ecosystem_uid,
    sensor_uid=hardware_uid,
    measure="humidity",
    value=42.0,
    timestamp=timestamp_now,
)


buffered_data_temperature = gv.BufferedSensorRecord(
    ecosystem_uid=ecosystem_uid,
    sensor_uid=hardware_uid,
    measure="temperature",
    value=25.0,
    timestamp=timestamp_now,
)


buffered_data_payload = gv.BufferedSensorsDataPayloadDict(
    uuid=request_uuid,
    data=[
        buffered_data_humidity,
        buffered_data_temperature,
    ],
)


light_state: gv.ActuatorStateDict = \
    {"active": True, "status": True, "mode": gv.ActuatorMode.automatic}
cooler_state: gv.ActuatorStateDict = \
    {"active": True, "status": False, "mode": gv.ActuatorMode.manual}
heater_state: gv.ActuatorStateDict = \
    {"active": False, "status": False, "mode": gv.ActuatorMode.automatic}
humidifier_state: gv.ActuatorStateDict = \
    {"active": False, "status": False, "mode": gv.ActuatorMode.automatic}
dehumidifier_state: gv.ActuatorStateDict = \
    {"active": False, "status": False, "mode": gv.ActuatorMode.automatic}


actuator_state_payload = gv.ActuatorsDataPayloadDict(
    uid=ecosystem_uid,
    data=gv.ActuatorsDataDict(
        light = light_state,
        cooler = cooler_state,
        heater = heater_state,
        humidifier = humidifier_state,
        dehumidifier = dehumidifier_state,
    )
)


place_dict = gv.Place(
    name= "home",
    coordinates= gv.Coordinates(4.0, 2.0),
)


places_payload = gv.PlacesPayloadDict(
    uid=engine_uid,
    data=[place_dict]
)
