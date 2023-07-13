from __future__ import annotations

from datetime import datetime, time, timezone

import gaia_validators as gv


ip_address = "127.0.0.1"
engine_sid = "engine_sid"
engine_uid = "engine_uid"
ecosystem_uid = "zutqsCKn"
ecosystem_name = "TestingEcosystem"
hardware_uid = "hardware_uid"


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
    "registration_date": datetime.now(timezone.utc),
    "last_seen": datetime.now(timezone.utc),
    "management": 0,
}


engine_dict = {
    "uid": engine_uid,
    "sid": engine_sid,
    "registration_date": (
        datetime.now(timezone.utc).replace(microsecond=0)
    ),
    "address": ip_address,
    "last_seen": datetime.now(timezone.utc),
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
    "webcam": False,
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
        gv.EnvironmentConfig(chaos=chaos, sky=sky, climate=[climate]).model_dump()
    )


hardware_data: gv.HardwareConfigDict = {
    "uid": hardware_uid,
    "name": "TestThermometer",
    "address": "GPIO_7",
    "type": gv.HardwareType.sensor.value,
    "level": gv.HardwareLevel.environment.value,
    "model": "virtualDHT22",
    "measures": ["temperature"],
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
    "hardware_uid",
    "temperature",
    42,
    None
)


sensors_data: gv.SensorsDataDict = {
    "timestamp": datetime.now(timezone.utc),
    "records": [sensor_record],
    "average": [measure_record]
}


sensors_data_payload: gv.SensorsDataPayloadDict = \
    wrap_ecosystem_data_payload(sensors_data)


health_data: gv.HealthRecord = gv.HealthRecord(
    0.57,
    0.15,
    0.85,
    datetime.now(timezone.utc)
)


health_data_payload: gv.HealthDataPayloadDict = \
    wrap_ecosystem_data_payload(health_data)


light_data: gv.LightDataDict = {
    "morning_start": datetime.now(timezone.utc).time(),
    "morning_end": datetime.now(timezone.utc).time(),
    "evening_start": datetime.now(timezone.utc).time(),
    "evening_end": datetime.now(timezone.utc).time(),
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
    "created_on": datetime.now(timezone.utc),
}


__all__ = (
    "base_info", "base_info_payload", "chaos", "climate", "ecosystem_dict",
    "ecosystem_name", "ecosystem_uid", "engine_dict", "engine_sid",
    "engine_uid", "environmental_payload", "hardware_data", "hardware_payload",
    "hardware_uid", "health_data", "health_data_payload", "ip_address", "light_data",
    "light_data_payload", "management_data", "management_payload",
    "measure_record", "sky", "sensor_record", "sensors_data",
    "sensors_data_payload", "turn_actuator_payload", "gaia_warning"
)
