from ouranos.services.template import ServiceTemplate


class DailyRecap(ServiceTemplate):
    LEVEL = "user"

    def _start(self) -> None:
        print("Todo: start daily recap")

    def _stop(self) -> None:
        print("Todo: stop daily recap")
