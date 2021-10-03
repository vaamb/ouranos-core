colors = {
  blue: "#226ba3",
  red: "#f0341f",
  yellow: "#e9c429",
}


parameters = {
    "subBoxesOrder": ["light", "environment", "plants"],
    "graphs": {
        "environment": {
            "colors": {"temperature": colors.red, "humidity": colors.blue, "absolute_humidity": colors.blue, "dew_point": colors.red, "light": colors.yellow},
            "icons": {"temperature": "fas fa-fire", "humidity": "fas fa-tint", "absolute_humidity":  "fas fa-tint", "dew_point": "fas fa-fire", "light": "fas fa-lightbulb"},
            "units": {"temperature": "°C", "humidity": "% humidity", "absolute_humidity": "g.m-3", "dew_point": "°C", "light": " lux"},
            "max_values": {"temperature": 35, "humidity": 100, "absolute_humidity": 30, "dew_point": 25, "light": 100000},
            "order": ["temperature", "humidity", "dew_point", "absolute_humidity", "light"],
        },
        "plants": {
            "colors": {"moisture": "#226ba3"},
            "icons": {"moisture": "fas fa-tint"},
            "units": {"moisture": "% RWC"},
            "max_values": {"moisture": 100},
        },
        "plants_health": {
            "measures": {"green": "Number of green pixels", "necrosis": "Necrosis percentage", "index": "Plants health index"},
            "colors": {"green": "#307a41", "necrosis": "#913639", "index": "#e9c429"},
            "icons": {"green": "fas fa-leaf", "necrosis": "fas fa-dizzy", "index": "fas fa-heartbeat"},
            "list_index": {"green": 2, "necrosis": 3, "index": 1},
            "max_values": {"green": 1000, "necrosis": 100, "index": 100},
        },
        "server": {
            "measures": {"CPU_used": "CPU load", "CPU_temp": "CPU temperature", "RAM_used": "Total RAM usage", "RAM_process": "Process RAM usage", "DISK_used": "Disk space used"},
            "colors": {"CPU_used": colors.blue, "CPU_temp": colors.red, "RAM_used": colors.blue, "DISK_used": colors.blue},
            "icons": {"CPU_used": "fas fa-microchip", "CPU_temp": "fas fa-fire", "RAM_used": "fas fa-memory", "DISK_used": "fas fa-database"},
            "units": {"CPU_used": "%", "CPU_temp": "°C", "RAM_used": "GB", "DISK_used": "GB"},
            "max_values": {"CPU_used": 100, "CPU_temp": 75},
        },
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

    setServerMaxValues: function(currentSystemData) {
      if (! currentSystemData.hasOwnProperty("CPU_temp")) {
        delete parameters.graphs.server.measures.CPU_temp;
      }
      const RAM_total = currentSystemData["RAM_total"];
      const DISK_total = currentSystemData["DISK_total"];
      Object.assign(parameters.graphs.server.max_values, {
        "RAM_used": RAM_total, "RAM_process": RAM_total, "DISK_used": DISK_total
      });
    },

    getOptions: function(option, level=null) {
      let rv = {};
      if (level) {
        try {
          Object.assign(rv, this.graphs[level][option]);
        } catch(e) {}
        return rv;
      }
      for (const e of Object.keys(this.graphs)) {
        try {
          Object.assign(rv, this.graphs[e][option]);
        } catch(e) {}
      }
      return rv;
    },
}
