from ouranos.sdk import Functionality, Plugin


class DummyFunctionality(Functionality):
    async def _startup(self):
        pass

    async def _shutdown(self):
        pass


dummy_plugin = Plugin(
    functionality=DummyFunctionality,
    name="dummy-plugin",
)
