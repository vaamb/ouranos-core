def start() -> None:
    print("Todo: start calendar")


def stop() -> None:
    print("Todo: stop calendar")


# TODO: send via socket.io a request to all engineManagers which will return webcamStream status and try to start it if off. 
# If fail to start webcamStream (for example because no webcam detected): send back a false to gaiaWeb. If all responses are false: auto turn off webcam service
