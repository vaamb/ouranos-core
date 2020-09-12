#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Change set_ecosystem_type and set_climate_type so when in moves from one to the other ...
change get_ecosystem_names to only show active environments"""
import ruamel.yaml
import datetime
import pytz
import random
import string

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "streamFormat":{
            "format": "%(asctime)s [%(levelname)-4.4s] %(name)-16.16s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
            },
        "fileFormat": {
            "format": "%(asctime)s -- %(levelname)s  -- %(name)s -- %(message)s",
            },
        },

    "handlers": {
        "streamHandler": {
            "level": "INFO",
            "formatter": "streamFormat",
            "class": "logging.StreamHandler",
            },
        "gaiaHandler": {
            "level": "INFO",
            "formatter": "fileFormat",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/gaia.log",
            "mode": "w",
            "maxBytes": 1024*512,
            "backupCount": 5,
            },
        "serverHandler": {
            "level": "INFO",
            "formatter": "fileFormat",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": "logs/server.log",
            "when": "W6",
            "interval": 1,
            "backupCount": 5
            },
        },

    "loggers": {      
        "gaia": {
            "handlers": ["streamHandler", "gaiaHandler"],
            "level": "INFO"
            },
        "eng": {
            "handlers": ["streamHandler", "gaiaHandler"],
            "level": "INFO"
            },            
        "apscheduler": {
            "handlers": ["streamHandler", "gaiaHandler"],
            "level": "WARNING"
            },
        "enginio.server": {
            "handlers": ["streamHandler", "serverHandler"],
            "level": "WARNING"
            },
        "socket.server": {
            "handlers": ["streamHandler", "serverHandler"],
            "level": "INFO"
            },
        "geventwebsocket": {
            "handlers": ["streamHandler", "gaiaHandler"],
            "level": "WARNING"
            },
        },
    }






class gaiaConfig():

    def __init__(self, ecosystem = None):
        self.ecosystem = ecosystem
        self._yaml = ruamel.yaml.YAML()
        try:
            self._ecosystems_config = self._load_file("config/ecosystems.cfg")
        except IOError:
            self._ecosystems_config = self._load_file("config/default.cfg")
            print("There is currently no custom config file. Using default file instead")
        self._private_config = self._load_file("config/private.cfg")

    """Private functions"""
    def _load_file(self, file_path):
        file = open(file_path, "r")
        file_loaded = self._yaml.load(file)
        file.close()
        return file_loaded

    def _update_private(self, section, value):
        self._private_config[section] = value
        self._save_config(self._private_config)
        pass

    def _save_config(self, config_to_save):
        if config_to_save == self._ecosystems_config:
            file = open("config/ecosystems.cfg", "w")
            self._yaml.dump(config_to_save, file)
            file.close()
        elif config_to_save == self._private_config:
            file = open("config/private.cfg", "w")
            self._yaml.dump(config_to_save, file)
            file.close()
        else:
            print("error")

    """Other"""
    def reset_config(self):
        self._ecosystems_config = self._load_file("config/default.cfg")
        pass #load default as ecosystems and save it as ecosystems

    """General informations needed for website"""
    def get_ecosystems(self):
        list = []
        for i in self._ecosystems_config.keys():
            list.append(i)
        return list
    
    def create_tag(self, ecosystem_or_sensor):
        if ecosystem_or_sensor == "ecosystem":
            k = 8
            used_tags = self.get_ecosystems()
        elif ecosystem_or_sensor == "sensor":
            k = 16
            used_tags = self.get_sensor_list(self, "environment")
            used_tags.append(self.get_sensor_list(self, "plant"))

        while True:
            x = "".join(random.choices(string.ascii_letters + string.digits, k=k))
            if x not in used_tags:
                break
        return x

    def get_active_ecosystems(self):
        list = []
        for ecosystem in self.get_ecosystems():
            if self._ecosystems_config[ecosystem]["status"] == "on":
                list.append(ecosystem)
        return list

    def get_ecosystems_with_webcam(self):
        list = []
        for ecosystem in self.get_active_ecosystems():
            if self._ecosystems_config[ecosystem]["webcam"]["status"] == "on":
                list.append(ecosystem)
        return list

    def tag_to_name_dict(self):
        dict = {}
        for ecosystem in self.get_ecosystems():
            dict[ecosystem] = self._ecosystems_config[ecosystem]["name"]
        return dict

    def name_to_tag_dict(self):
        dict = self.tag_to_name_dict()
        inv_dict = {v: k for k, v in dict.items()}
        return inv_dict

    """Ecosystems related parameters"""
    def get_status(self):
        return self._ecosystems_config[self.ecosystem]["status"]

    def set_status(self, new_status):
        if new_status in ["on", "off"]:
            self._ecosystems_config[self.ecosystem]["status"] = new_status
            self._save_config(self._ecosystems_config)
        else:
            return "Status can either be 'on' or 'off'"
    
    def get_ecosystem_type(self):
        return self._ecosystems_config[self.ecosystem]["environment"]["type"]

    def set_ecosystem_type(self, eco_type):
        if eco_type in ["active", "passive"]:
            self._ecosystems_config[self.ecosystem]["environment"]["type"] = eco_type
            self._save_config(self._ecosystems_config)
        else:
            return "Ecosystem type can either be 'active' or 'passive'"

    def get_plants(self):
        return self._ecosystems_config[self.ecosystem]["plants"]

    def set_plants(self, plants):
        self._ecosystems_config[self.ecosystem]["plants"] = plants
        self._save_config(self._ecosystems_config)

    """Hardware related parameters"""
    def get_hardware_list(self):
        list = []
        for key in self._ecosystems_config[self.ecosystem]["IO"].keys():
            list.append(key)
        return list

    def address_to_name_dict(self):
        dict = {}
        for hardware in self.get_hardware_list():
            dict[hardware] = self._ecosystems_config[self.ecosystem]["IO"][hardware]["name"]
        return dict

    def name_to_address_dict(self):
        dict = self.address_to_name_dict()
        inv_dict = {v: k for k, v in dict.items()}
        return inv_dict

    def get_hardware_pin(self, hardware):
        return self._ecosystems_config[self.ecosystem]["IO"][hardware]["pin"]

    def get_hardware_model(self, hardware):
        return self._ecosystems_config[self.ecosystem]["IO"][hardware]["model"]

    def get_sensor_dict(self):
        dict = {}
        for hardware in self._ecosystems_config[self.ecosystem]["IO"].keys():
            if self._ecosystems_config[self.ecosystem]["IO"][hardware]["type"] == "sensor":
               dict[hardware] = self._ecosystems_config[self.ecosystem]["IO"][hardware]
        return dict

    def get_sensor_list(self, environment_or_plant):
        list = []
        for hardware in self._ecosystems_config[self.ecosystem]["IO"].keys():
            if (self._ecosystems_config[self.ecosystem]["IO"][hardware]["level"] == environment_or_plant
                and self._ecosystems_config[self.ecosystem]["IO"][hardware]["type"] == "sensor"):
                list.append(hardware)
        return list

    def get_measure_list(self, environment_or_plant):
        mylist = []
        for sensor in self.get_sensor_list(environment_or_plant):
            data = self._ecosystems_config[self.ecosystem]["IO"][sensor]["measure"]
            if type(data) == str:
                mylist.append(data)
            else:
                for subdata in data:
                    mylist.append(subdata)
        return mylist

    def get_sensors_for_measure(self, environment_or_plant, measure):
        if environment_or_plant == "environment":
            sensors = []
            for sensor in self.get_sensor_list(environment_or_plant):
                measures = self._ecosystems_config[self.ecosystem]["IO"][sensor]["measure"]
                if measure in measures:
                    sensors.append(sensor)
            return sensors
        elif environment_or_plant == "plant":
            sensors = []
            for sensor in self.get_sensor_list(environment_or_plant):
                measures = self._ecosystems_config[self.ecosystem]["IO"][sensor]["plant"]
                if measure in measures:
                    sensors.append(sensor)
            return sensors

    def get_plants_with_sensor(self):
        plant_sensors = self.get_sensor_list("plant")
        list = []
        for plant_sensor in plant_sensors:
            list.append(self._ecosystems_config[self.ecosystem]["IO"][plant_sensor]["plant"])
        return list

    """Light related  parameters"""
    def _config_to_time(self, time_formatted):
        hours, minutes = time_formatted.split("h")
        return datetime.time(int(hours), int(minutes))

    def _time_to_utc_datetime(self, mytime):
        mydatetime = datetime.datetime.combine(datetime.date.today(), mytime)
        utc_datetime = pytz.utc.localize(mydatetime)
        return utc_datetime

    def _utc_to_local(self, mydatetime):
        return mydatetime.astimezone(pytz.timezone(self.get_local_timezone()))
        
    def get_light_parameters(self):
        dict = {}
        day = self._ecosystems_config[self.ecosystem]["environment"]["day_start"]
        dict["day"] = self._config_to_time(day)
        night = self._ecosystems_config[self.ecosystem]["environment"]["night_start"]
        dict["night"] = self._config_to_time(night)
        hours, minutes = self._ecosystems_config[self.ecosystem]["environment"]["sun_offset"].split("h")
        dict["sun_offset"] = datetime.timedelta(hours = int(hours), minutes = int(minutes))
        return dict

    def set_light_parameters(self, day_start, night_start, sun_offset):
        self._ecosystems_config[self.ecosystem]["environment"]["day_start"] = day_start
        self._ecosystems_config[self.ecosystem]["environment"]["night_start"] = night_start
        self._ecosystems_config[self.ecosystem]["environment"]["sun_offset"] = sun_offset
        self._save_config(self._ecosystems_config)
        
    def utc_time_to_local_time(self, mytime):
        mydatetime = datetime.datetime.combine(datetime.date.today(), mytime)
        mydatetime = pytz.utc.localize(mydatetime)
        local_time = mydatetime.astimezone(pytz.timezone(self.get_local_timezone())).time()
        return local_time
        
    def get_sun_times(self):
        def import_daytime_event(daytime_event):
            sunrise = self._load_file("cache/sunrise.cch")
            mytime = datetime.datetime.strptime(sunrise[daytime_event], "%I:%M:%S %p").time()
            local_time = self.utc_time_to_local_time(mytime)
            return local_time
        dict = {}
        dict["twilight_begin"] = import_daytime_event("civil_twilight_begin")
        dict["sunrise"] = import_daytime_event("sunrise")
        dict["sunset"] = import_daytime_event("sunset")
        dict["twilight_end"] = import_daytime_event("civil_twilight_end")
        return dict

    '''Environment related parameters'''
    def get_climate_type(self):
        return self._ecosystems_config[self.ecosystem]["environment"]["control"]

    def set_climate_type(self, new_climate_type):
        climate_type = self.get_climate_type()
     
        if new_climate_type in ["day&night", "continuous"]:
            self._ecosystems_config[self.ecosystem]["environment"]["control"] = new_climate_type
            if climate_type == "continuous":
                self._ecosystems_config[self.ecosystem]["environment"]["day"] = self._ecosystems_config[self.ecosystem]["environment"]["continuous"]
                self._ecosystems_config[self.ecosystem]["environment"]["night"] = self._ecosystems_config[self.ecosystem]["environment"]["continuous"]
                del(self._ecosystems_config[self.ecosystem]["environment"]["continuous"])

            else:
                self._ecosystems_config[self.ecosystem]["environment"]["continuous"] = self._ecosystems_config[self.ecosystem]["environment"]["day"]
                del(self._ecosystems_config[self.ecosystem]["environment"]["day"])
            self._save_config(self._ecosystems_config)
        else:
            return "Climate type can either be 'day&night' or 'continuous'"

    def get_climate_parameters(self, temp_or_hum):
        dict = {}
        climate_type = self.get_climate_type()
        ecosystem_type = self.get_ecosystem_type()
        if temp_or_hum in ["temperature", "humidity"]:
            if climate_type == "continuous":
                if ecosystem_type == "active":
                    dict = self._ecosystems_config[self.ecosystem]["environment"]["continuous"][temp_or_hum]
                else: #if ecosystem_type == "passive
                    for min_or_max in ["min", "max"]:
                        dict[min_or_max] = self._ecosystems_config[self.ecosystem]["environment"]["continuous"][temp_or_hum][min_or_max]
            else: #if climate_type == "day&night"
                if ecosystem_type == "active":
                    for day_or_night in ["day", "night"]:
                        dict[day_or_night] = self._ecosystems_config[self.ecosystem]["environment"][day_or_night][temp_or_hum]
                else: #if ecosystem_type == "passive
                    for day_or_night in ["day", "night"]:
                        dict[day_or_night] = {}
                        for min_or_max in ["min", "max"]:
                            dict[day_or_night][min_or_max] = self._ecosystems_config[self.ecosystem]["environment"][day_or_night][temp_or_hum][min_or_max]
            return dict
        else:
            return "Type of climate parameter can either be 'temperature' or 'humidity'"

    def set_climate_parameters(self, temp_or_hum, value):
        climate_type = self.get_climate_type()
        if climate_type == "continuous":
            self._ecosystems_config[self.ecosystem]["environment"]["continuous"][temp_or_hum] = value
        else: #if climate_type == "day&night"
            for day_or_night in ["day", "night"]:
                    self._ecosystems_config[self.ecosystem]["environment"][day_or_night][temp_or_hum] = value[day_or_night]



    """Private config parameters"""
    def get_user(self):
        return self._private_config["user"] if "user" in self._private_config else {"firstname": "John", "lastname": "Doe"}
    
    def set_user(self, firstname, lastname):
        mydict = {"firstname": firstname, "lastname": lastname}
        self._update_private("user", mydict)
    
    def get_home_coordinates(self):
        return self._private_config["places"]["home"]["coordinates"] if "home" in self._private_config["places"] else {"latitude": 0, "longitude": 0}

    def set_home_coordinates(self, latitude, longitude):
        mydict = {"latitude": latitude, "longitude": longitude}
        pass

    def get_home_city(self):
        return self._private_config["places"]["home"]["city"] if "home" in self._private_config["places"] else "Somewhere over the rainbow"

    def get_local_timezone(self):
        return str(self._private_config["timezone"]) if "timezone" in self._private_config else None

    def set_local_timezone(self, timezone):
        self._update_private("timezone", timezone)

    def get_weather_APIcode(self):
        return str(self._private_config["darksky_APIcode"]) if "darksky_APIcode" in self._private_config else None

    def set_weather_APIcode(self, APIcode):
        self._update_private("darksky_APIcode", APIcode)

    def get_database_info(self):
        return self._private_config["database"] if "database" in self._private_config else None

    def set_database_info(self, host, db, user, passwd):
        mydict = {"host": host, "db": db, "user": user, "passwd": passwd}
        self._update_private("database", mydict)
    
    def get_telegram_info(self):
        return self._private_config["telegram_API"] if "telegram_API" in self._private_config else None

if __name__ == "__main__":
    config = gaiaConfig()
    print(config.get_weather_APIcode())