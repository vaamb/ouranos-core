from ouranos.sdk import Functionality, Plugin


class DummyFunctionality(Functionality):
    def _start(self):
        pass

    def _stop(self):
        pass


dummy_plugin = Plugin(
    functionality=DummyFunctionality,
    name="dummy-plugin",
)
