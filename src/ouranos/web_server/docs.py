description = """
### Ouranos API helps you to manage multiple instances of Gaia (which is looking after your plants 🌱)

The following options are available

### App 📱

Get information about the current app (such as its version, the services
available ...)

### Auth 🔒

Register, login and get information about the current user

### User 🧑

Get and update information about the users

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
        "name": "app/services/calendar",
        "description": "Create and manage the calendar",
    },
    {
        "name": "app/services/weather",
        "description": "Weather-related info. Rem: it returns data only if "
                       "the weather service has been enabled",
    },
    {
        "name": "app/services/wiki",
        "description": "Create, update and get wiki articles",
    },
    {
        "name": "auth",
        "description": "Authenticate and log user to access protected paths",
    },
    {
        "name": "user",
        "description": "Get information about the users and update them",
    },
    {
        "name": "gaia/engine",
        "description": "Consult the info about Gaia's registered engine"
    },
    {
        "name": "gaia/ecosystem",
        "description": "Manage Gaia's registered ecosystems. Rem creating, "
                       "updating and deleting ecosystems require to be logged "
                       "in as an operator",
    },
    {
        "name": "gaia/camera_picture_info",
        "description": "Information about the camera pictures available on the "
                       "static endpoint",
    },
    {
        "name": "gaia/ecosystem/hardware",
        "description": "Manage the hardware in Gaia's ecosystems. Rem creating, "
                       "updating and deleting hardware require to be logged in "
                       "as an operator",
    },
    {
        "name": "gaia/ecosystem/sensor",
        "description": "Consult Gaia's sensors info and data",
    },
    {
        "name": "gaia/warning",
        "description": "Get Gaia's warnings",
    },
    {
        "name": "system",
        "description": "Server-related info. Rem: it requires to be logged "
                       "in as an administrator",
    },
]