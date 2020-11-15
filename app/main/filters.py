from datetime import datetime

from app.main import bp


@bp.app_template_filter('getDay')
def get_day(s):
    return datetime.fromtimestamp(s).strftime("%A %d %B")


@bp.app_template_filter('getTime')
def get_time(s):
    x = datetime.fromtimestamp(s)
    return"{}:{:02d}".format(x.hour, x.minute)  # somehow, use .strftime("%H:%S") returns the same value for the whole page


@bp.app_template_filter('getWeatherIcon')
def get_weather_icon(weather):
    translation ={"clear-day":"wi wi-day-sunny",
                  "clear-night":"wi wi-night-clear", 
                  "rain":"wi wi-rain", 
                  "snow":"wi wi-snow", 
                  "sleet":"wi wi-sleet", 
                  "wind":"wi wi-cloudy-gusts", 
                  "fog":"wi wi-fog", 
                  "cloudy":"wi wi-cloudy", 
                  "partly-cloudy-day":"wi wi-day-cloudy", 
                  "partly-cloudy-night":"wi wi-night-alt-cloudy",
                  }
    return translation[weather]

@bp.app_template_filter('humanizeList')
def humanize_list(list):
    list_length = len(list)
    sentence = []
    for i in range(list_length):
        sentence.append(list[i])
        if i < list_length - 2:
            sentence.append(", ")
        elif i == list_length - 2:
            sentence.append(" and ")
    return("".join(sentence))

@bp.app_template_filter('roundDecimals')
def round_to_decimals(x):
    rounded = round(x, 1)
    return "{:.1f}".format(rounded)

@bp.app_template_filter('tryKeys')
def try_dict(x):
    try:
        return x
    except KeyError:
        pass
