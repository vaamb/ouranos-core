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
        "max_value": {"green": 1000, "necrosis": 100, "index": 100},
    },
    "server": {
        "measure": {"CPU_used": "CPU load", "CPU_temp": "CPU temperature", "RAM_used": "RAM usage", "DISK_used": "Disk space used"},
        "color": {"CPU_used": "#307a41", "CPU_temp": "#307a41", "RAM_used": "#913639", "DISK_used": "#e9c429"},
        "icon": {"CPU_used": "fas fa-microchip", "CPU_temp": "fas fa-fire", "RAM_used": "fas fa-memory", "DISK_used": "fas fa-database"},
        "unit": {"CPU_used": "%", "CPU_temp": "°C", "RAM_used": "GB", "DISK_used": "GB"},
        "list_index": {"CPU_used": 1, "CPU_temp": 2, "RAM_used": 3, "DISK_used": 5},
    },
    
}
