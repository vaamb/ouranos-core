function capitalize(s) {
  if (typeof s !== 'string') return ''
  return s.charAt(0).toUpperCase() + s.slice(1)
}

jQuery.fn.insertAt = function(index, element) {
  let lastIndex = this.children().length;
  if (index < 0) {
    index = Math.max(0, lastIndex + 1 + index);
  }
  this.append(element);
  if (index < lastIndex) {
    this.children().eq(index).before(this.children().last());
  }
  return this;
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

utils = {
  getWeatherIconClass: function(iconName) {
    return WeatherIconTranslation[iconName]
  }
}

