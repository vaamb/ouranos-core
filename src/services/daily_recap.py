from src.services.template import serviceTemplate


class dailyRecap(serviceTemplate):
    NAME = "daily_recap"
    LEVEL = "user"

    def _start(self) -> None:
        print("Todo: start daily recap")

    def _stop(self) -> None:
        print("Todo: stop daily recap")
