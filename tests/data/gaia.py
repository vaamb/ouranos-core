from __future__ import annotations

from datetime import timezone

from gaia_validators import *


ip_address = "127.0.0.1"
engine_sid = "engine_sid"
engine_uid = "engine_uid"
ecosystem_uid = "zutqsCKn"
ecosystem_name = "TestingEcosystem"


def wrap_ecosystem_data_payload(data: dict | list[dict]) -> dict:
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


base_info: BaseInfoConfigDict = {
    "engine_uid": engine_uid,
    "uid": ecosystem_uid,
    "name": ecosystem_name,
    "status": True,
}


base_info_payload: BaseInfoConfigPayloadDict = \
    wrap_ecosystem_data_payload(base_info)


management_data: ManagementConfigDict = {
    "sensors": True,
    "light": True,
    "climate": True,
    "watering": False,
    "health": False,
    "database": False,
    "alarms": False,
    "webcam": False,
}


management_payload: ManagementConfigPayloadDict = \
    wrap_ecosystem_data_payload(management_data)


chaos: ChaosConfigDict = {
    "frequency": 10,
    "duration": 2,
    "intensity": 0.2,
}


sky: SkyConfigDict = {
    "day": time(6, 0),
    "night": time(22, 0),
    "lighting": LightMethod.elongate,
}


climate: ClimateConfigDict = {
    "parameter": "temperature",
    "day": 42,
    "night": 21,
    "hysteresis": 5,
}


environmental_payload: EnvironmentConfigPayloadDict = \
    wrap_ecosystem_data_payload(
        EnvironmentConfig(chaos=chaos, sky=sky, climate=[climate]).dict()
    )


hardware_data: HardwareConfigDict = {
    "uid": "hardware_uid",
    "name": "TestThermometer",
    "address": "GPIO_7",
    "type": HardwareType.sensor,
    "level": HardwareLevel.environment,
    "model": "virtualDHT22",
    "measures": ["temperature"],
    "plants": [],
    "multiplexer_model": None,
}


hardware_payload: HardwareConfigPayloadDict = \
    wrap_ecosystem_data_payload([hardware_data])


measure_record: MeasureRecordDict = {
    "measure": "temperature",
    "value": 42
}


sensor_record: SensorRecordDict = {
    "sensor_uid": "hardware_uid",
    "measures": [measure_record]
}


sensors_data: SensorsDataDict = {
    "timestamp": datetime.now(timezone.utc),
    "records": [sensor_record],
    "average": [measure_record]
}


sensors_data_payload: SensorsDataPayloadDict = \
    wrap_ecosystem_data_payload(sensors_data)


health_data: HealthDataDict = {
    "timestamp": datetime.now(timezone.utc),
    "green": 0.57,
    "necrosis": 0.15,
    "index": 0.85,
}


health_data_payload: HealthDataPayloadDict = \
    wrap_ecosystem_data_payload(health_data)


light_data: LightDataDict = {
    "morning_start": datetime.now(timezone.utc).time(),
    "morning_end": datetime.now(timezone.utc).time(),
    "evening_start": datetime.now(timezone.utc).time(),
    "evening_end": datetime.now(timezone.utc).time(),
    "status": False,
    "mode": ActuatorMode.automatic,
    "method": LightMethod.elongate,
    "timer": 0.0,
}


light_data_payload: LightDataPayloadDict = \
    wrap_ecosystem_data_payload(light_data)


turn_actuator_payload: TurnActuatorPayloadDict = {
    "ecosystem_uid": ecosystem_uid,
    "actuator": HardwareType.light,
    "mode": ActuatorMode.automatic,
    "countdown": 0.0,
}

__all__ = (
    "base_info", "base_info_payload", "chaos", "climate", "ecosystem_dict",
    "ecosystem_name", "ecosystem_uid", "engine_dict", "engine_sid",
    "engine_uid", "environmental_payload", "hardware_data", "hardware_payload",
    "health_data", "health_data_payload", "ip_address", "light_data",
    "light_data_payload", "management_data", "management_payload",
    "measure_record", "sky", "sensor_record", "sensors_data",
    "sensors_data_payload", "turn_actuator_payload"
)
