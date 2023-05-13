from datetime import datetime, timezone

from gaia_validators import (
    ActuatorMode, EnvironmentConfig, HardwareLevel, HardwareType, LightMethod)


ip_address = "127.0.0.1"
engine_sid = "engine_sid"
engine_uid = "engine_uid"
ecosystem_uid = "zutqsCKn"


def wrap_ecosystem_data_payload(data: dict) -> dict:
    return {
        "uid": ecosystem_uid,
        "data": data,
    }


base_info = {
    "engine_uid": engine_uid,
    "uid": ecosystem_uid,
    "name": "Test Ecosystem",
    "status": True,
}


base_info_payload = wrap_ecosystem_data_payload(base_info)


management = {
    "sensors": True,
    "light": True,
    "climate": True,
    "watering": True,
    "health": True,
    "database": True,
    "alarms": True,
    "webcam": True,
}


management_payload = wrap_ecosystem_data_payload(management)


environmental_payload = wrap_ecosystem_data_payload(EnvironmentConfig().dict())


hardware = {
    "uid": "hardware_uid",
    "name": "TestThermometer",
    "address": "GPIO_7",
    "type": HardwareType.sensor.value,
    "level": HardwareLevel.environment.value,
    "model": "virtualDHT22",
    "measures": ["temperature"],
    "plants": [],
    "multiplexer_model": None,
}


hardware_payload = wrap_ecosystem_data_payload(hardware)


sensors_data = {
    "timestamp": datetime.now(timezone.utc),
    "records": [
        {
            "sensor_uid": "hardware_uid",
            "measures": [
                {"measure": "temperature", "value": 42}
            ]
        }
    ],
    "average": [{"measure": "temperature", "value": 42}]
}


sensors_data_payload = wrap_ecosystem_data_payload(sensors_data)


health_data = {
    "timestamp": datetime.now(timezone.utc),
    "green": 0.57,
    "necrosis": 0.15,
    "index": 0.85,
}


health_data_payload = wrap_ecosystem_data_payload(health_data)


light_data = {
    "morning_start": datetime.now(timezone.utc).time(),
    "morning_end": datetime.now(timezone.utc).time(),
    "evening_start": datetime.now(timezone.utc).time(),
    "evening_end": datetime.now(timezone.utc).time(),
    "status": False,
    "mode": ActuatorMode.automatic,
    "method": LightMethod.elongate,
    "timer": 0.0,
}


light_data_payload = wrap_ecosystem_data_payload(light_data)


turn_actuator_payload = {
    "ecosystem_uid": ecosystem_uid,
    "actuator": HardwareType.light,
    "mode": ActuatorMode.automatic,
    "countdown": 0.0,
}
