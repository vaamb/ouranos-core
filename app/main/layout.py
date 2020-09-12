'''
Small module to customize graphs colors for the different html pages
'''

parameters = {
    "environment": {
        "color": {"temperature": "#f0341f", "humidity": "#226ba3", "light": "#e9c429"},
        "icon": {"temperature": "fas fa-fire", "humidity": "fas fa-tint", "light": "fas fa-lightbulb"},
        "unit": {"temperature": "°C", "humidity": "% humidity", "light": " lux"},
        "max_value": {"temperature": 35, "humidity": 100, "light": 10000},
    },
    "plants": {
        "color": {"moisture": "#226ba3"},
        "icon": {"moisture": "fas fa-tint"},
        "unit": {"moisture": "RWC"},
        "max_value": {"moisture": 100},
    },
    "plants_health": {
        "measure": {"green": "Number of green pixels", "necrosis": "Necrosis percentage", "index": "Plants health index"},
        "color": {"green": "#307a41", "necrosis": "#913639", "index": "#e9c429"},
        "icon": {"green": "fas fa-leaf", "necrosis": "fas fa-dizzy", "index": "fas fa-heartbeat"},
        "list_index": {"green": 2, "necrosis": 3, "index": 1},
        "max_value": {"green": 8081920, "necrosis": 100, "index": 100},
    },
    "server": {
        "measure": {"CPU": "CPU load", "RAM_used": "RAM usage", "DISK_used": "Disk space used"},
        "color": {"CPU": "#307a41", "RAM_used": "#913639", "DISK_used": "#e9c429"},
        "icon": {"CPU": "fas fa-microchip", "RAM_used": "fas fa-memory", "DISK_used": "fas fa-database"}, 
        "unit": {"CPU": "%", "RAM_used": "GB", "DISK_used": "GB"},
        "list_index": {"CPU": 1, "RAM_used": 3, "DISK_used": 5},
    },
    
}
