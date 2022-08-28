description = """
### Ouranos API helps you to manage multiple instances of Gaia which are looking after your plants 🌱

The following options are available

### App 📱

Get information about the current app (such as its version, the services
available ...)

### Auth 🧑

Register, login and get information about the current user

### Gaia 🌿

Get information and manage the instances of Gaia that are connected here

### System 🐋

Get information about the servers on which Ouranos is running

### Weather 🌤️

When the weather service is enable, get weather forecast, and sunrise and 
sunset times
"""

tags_metadata = [
    {
        "name": "app",
        "description": "App-related info",
    },
    {
        "name": "auth",
        "description": "Authenticate and log user to access protected paths",
    },
    {
        "name": "gaia",
        "description": "Manage Gaia's registered ecosystems",
    },
    {
        "name": "system",
        "description": "Server-related info. Rem: it requires to be logged "
                       "in as an administrator",
    },
    {
        "name": "weather",
        "description": "Weather-related info. Rem: it returns data only if "
                       "the weather service has been enabled",
    },
]