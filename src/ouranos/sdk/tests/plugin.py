from ouranos.sdk import Functionality, Plugin


class DummyFunctionality(Functionality):
    def __init__(self, manager_dict = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dict = {} if manager_dict is None else manager_dict
        self.dict["value"] = None

    async def _startup(self):
        self.dict["value"] = 42
        x = 1

    async def _shutdown(self):
        self.dict["value"] = None


dummy_plugin = Plugin(
    functionality=DummyFunctionality,
    name="dummy-plugin",
)
