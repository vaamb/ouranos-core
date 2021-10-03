import json
import pathlib

parameters = {
    "subBoxesOrder": ["light", "environment", "plants"],
    "environment": {
        "color": {"temperature": "#f0341f", "humidity": "#226ba3", "absolute_humidity": "#226ba3", "dew_point": "#f0341f", "light": "#e9c429"},
        "icon": {"temperature": "fas fa-fire", "humidity": "fas fa-tint", "absolute_humidity":  "fas fa-tint", "dew_point": "fas fa-fire", "light": "fas fa-lightbulb"},
        "unit": {"temperature": "°C", "humidity": "% humidity", "absolute_humidity": "g.m-3", "dew_point": "°C", "light": " lux"},
        "max_value": {"temperature": 35, "humidity": 100, "absolute_humidity": 30, "dew_point": 25, "light": 100000},
    },
    "plants": {
        "color": {"moisture": "#226ba3"},
        "icon": {"moisture": "fas fa-tint"},
        "unit": {"moisture": "% RWC"},
        "max_value": {"moisture": 100},
    },
    "plants_health": {
        "measure": {"green": "Number of green pixels", "necrosis": "Necrosis percentage", "index": "Plants health index"},
        "color": {"green": "#307a41", "necrosis": "#913639", "index": "#e9c429"},
        "icon": {"green": "fas fa-leaf", "necrosis": "fas fa-dizzy", "index": "fas fa-heartbeat"},
        "list_index": {"green": 2, "necrosis": 3, "index": 1},
        "max_value": {"green": 1000, "necrosis": 100, "index": 100},
    },
    "server": {
        "measure": {"CPU_used": "CPU load", "CPU_temp": "CPU temperature", "RAM_used": "RAM usage", "DISK_used": "Disk space used"},
        "color": {"CPU_used": "#307a41", "CPU_temp": "#307a41", "RAM_used": "#913639", "DISK_used": "#e9c429"},
        "icon": {"CPU_used": "fas fa-microchip", "CPU_temp": "fas fa-fire", "RAM_used": "fas fa-memory", "DISK_used": "fas fa-database"},
        "unit": {"CPU_used": "%", "CPU_temp": "°C", "RAM_used": "GB", "DISK_used": "GB"},
        "list_index": {"CPU_used": 1, "CPU_temp": 2, "RAM_used": 3, "DISK_used": 5},
    },
    "WeatherIconTranslation": {
        "clear-day": "wi wi-day-sunny",
        "clear-night": "wi wi-night-clear",
        "rain": "wi wi-rain",
        "snow": "wi wi-snow",
        "sleet": "wi wi-sleet",
        "wind": "wi wi-cloudy-gusts",
        "fog": "wi wi-fog",
        "cloudy": "wi wi-cloudy",
        "partly-cloudy-day": "wi wi-day-cloudy",
        "partly-cloudy-night": "wi wi-night-alt-cloudy",
    },
}

script_path = pathlib.Path(__file__).absolute()
js_path = script_path.parents[1]/"app/static/js/parameters.js"
print(js_path)
update = False
try:
    if script_path.stat().st_mtime > js_path.stat().st_mtime:
        update = True
except FileNotFoundError:
    update = True
if update:
    with open(script_path, "w") as file:
        json.dump(parameters, file, indent=4)
