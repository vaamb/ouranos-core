from ouranos.sdk import Functionality, Plugin


class DummyFunctionality(Functionality):
    def _startup(self):
        pass

    def _shutdown(self):
        pass


dummy_plugin = Plugin(
    functionality=DummyFunctionality,
    name="dummy-plugin",
)
