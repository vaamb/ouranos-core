function capitalize(s) {
  if (typeof s !== 'string') return ''
  return s.charAt(0).toUpperCase() + s.slice(1)
}

let WeatherIconTranslation = {
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
}

function getWeatherIconClass(iconName) {
  return WeatherIconTranslation[iconName]
}

function extractHistoricSystemData(data) {
  let result = {
    "datetime": [],
    "CPU_used": [],
    "CPU_temp": [],
    "RAM_used": [],
    "DISK_used": []
  }
  for (const elem in data) {
    if (Array.isArray(data[elem])) {
      result["datetime"].push(new Date(data[elem][0]));
      result["CPU_used"].push(data[elem][1]);
      result["CPU_temp"].push(data[elem][2]);
      result["RAM_used"].push(data[elem][3]);
      result["DISK_used"].push(data[elem][5]);
    } else if (typeof data[elem] === "object" && data[elem] !== null) {
      result["datetime"].push(new Date(data[elem]["datetime"]));
      result["CPU_used"].push(data[elem]["CPU_used"]);
      result["CPU_temp"].push(data[elem]["CPU_temp"]);
      result["RAM_used"].push(data[elem]["RAM_used"]);
      result["DISK_used"].push(data[elem]["DISK_used"]);
    } else {
      console.log("Unexpected data format in historicSystemData");
    }
  }
  if (Math.max(...result["CPU_temp"]) === 0) {
    delete result["CPU_temp"]
  }
  return result
}
