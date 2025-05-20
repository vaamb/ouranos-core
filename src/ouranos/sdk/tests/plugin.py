from ouranos.sdk import Functionality, Plugin


class DummyFunctionality(Functionality):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = None

    async def _startup(self):
        self.value = 42

    async def _shutdown(self):
        self.value = None


dummy_plugin = Plugin(
    functionality=DummyFunctionality,
    name="dummy-plugin",
)
