from __future__ import annotations

import uuid
from typing import NamedTuple

from datetime import datetime, time, timedelta, timezone

import gaia_validators as gv


timestamp_now = datetime.now(timezone.utc)
ip_address = "127.0.0.1"
engine_sid = uuid.uuid4()
engine_uid = "engine_uid"
ecosystem_uid = "zutqsCKn"
ecosystem_name = "TestingEcosystem"
plant_uid = "plant_uid"
hardware_uid = "hardware_uid"
measure_name = "temperature"
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
    "camera": True,
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


chaos_payload = wrap_ecosystem_data_payload(chaos)


sky: gv.NycthemeralCycleConfigDict = {
    "day": time(6, 0),
    "night": time(22, 0),
    "lighting": gv.LightingMethod.elongate,
    "span": gv.NycthemeralSpanMethod.fixed,
    "target": ""
}


climate: gv.ClimateConfigDict = {
    "parameter": "temperature",
    "day": 42,
    "night": 21,
    "hysteresis": 5,
    "alarm": None,
}


climate_payload = wrap_ecosystem_data_payload([climate])


environmental_payload: gv.EnvironmentConfigPayloadDict = \
    wrap_ecosystem_data_payload(
        gv.EnvironmentConfig(
            chaos=chaos,
            nycthemeral_cycle=sky,
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
    "plants": [plant_uid],
    "multiplexer_model": None,
}


camera_config: gv.HardwareConfigDict = {
    "uid": "camera_uid",
    "name": "TestCamera",
    "address": "PICAMERA",
    "type": gv.HardwareType.camera.name,
    "level": gv.HardwareLevel.ecosystem.name,
    "model": "virtualDHT22",
    "measures": ["MPRI|"],
    "plants": [],
    "multiplexer_model": None,
}


hardware_payload: gv.HardwareConfigPayloadDict = \
    wrap_ecosystem_data_payload([hardware_data])


plant_data: gv.PlantConfigDict = {
    "uid": plant_uid,
    "name": "TestPlant",
    "species": "TestSpecies",
    "sowing_date": timestamp_now,
    "hardware": [hardware_uid],
}


plants_payload: gv.PlantConfigPayloadDict = \
    wrap_ecosystem_data_payload([plant_data])


measure_record = gv.MeasureAverage(
    measure_name,
    42,
    None
)


sensor_record = gv.SensorRecord(
    hardware_uid,
    measure_name,
    42,
    None,
)


actuator_record = gv.ActuatorStateRecord(
    gv.HardwareType.light,
    True,
    gv.ActuatorMode.manual,
    True,
    0.42,
    timestamp_now - timedelta(minutes=33),
)


alarm_record = gv.SensorAlarm(
    sensor_uid=hardware_uid,
    measure=measure_name,
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


health_record: gv.HealthRecord = gv.HealthRecord(
    sensor_uid="camera_uid",
    measure="MPRI",
    value=0.789,
    timestamp=timestamp_now,
)


health_data: gv.HealthDataDict = {
    "timestamp": timestamp_now,
    "records": [health_record],
}


health_data_payload: gv.HealthDataPayloadDict = \
    wrap_ecosystem_data_payload(health_data)


light_data: gv.LightingHoursDict = {
    "morning_start": timestamp_now.time(),
    "morning_end": timestamp_now.time(),
    "evening_start": timestamp_now.time(),
    "evening_end": timestamp_now.time(),
}


light_data_payload: gv.LightDataPayloadDict = \
    wrap_ecosystem_data_payload(light_data)


nycthemeral_info_payload = wrap_ecosystem_data_payload({**sky, **light_data})


turn_actuator_payload: gv.TurnActuatorPayloadDict = {
    "ecosystem_uid": ecosystem_uid,
    "actuator": gv.HardwareType.light,
    "mode": gv.ActuatorModePayload.automatic,
    "countdown": 0.0,
}


gaia_warning = {
    "level": gv.WarningLevel.low,
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
    measure=measure_name,
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


def get_actuator_state(actuator_type: gv.HardwareType) -> gv.ActuatorStateRecord:
    return gv.ActuatorStateRecord(
        type=actuator_type,
        active=True,
        mode=gv.ActuatorMode.automatic,
        status=False,
        level=42.0,
        timestamp=timestamp_now,
    )


light_state: gv.ActuatorStateRecord = get_actuator_state(gv.HardwareType.light)
cooler_state: gv.ActuatorStateRecord = get_actuator_state(gv.HardwareType.cooler)
heater_state: gv.ActuatorStateRecord = get_actuator_state(gv.HardwareType.heater)
humidifier_state: gv.ActuatorStateRecord = get_actuator_state(gv.HardwareType.humidifier)
dehumidifier_state: gv.ActuatorStateRecord = get_actuator_state(gv.HardwareType.dehumidifier)
fan_state: gv.ActuatorStateRecord = get_actuator_state(gv.HardwareType.fan)


actuator_state_payload = gv.ActuatorsDataPayloadDict(
    uid=ecosystem_uid,
    data=[
        light_state,
        cooler_state,
        heater_state,
        humidifier_state,
        dehumidifier_state,
        fan_state,
    ]
)


place_dict = gv.Place(
    name= "home",
    coordinates= gv.Coordinates(4.0, 2.0),
)


places_payload = gv.PlacesPayloadDict(
    uid=engine_uid,
    data=[place_dict]
)
