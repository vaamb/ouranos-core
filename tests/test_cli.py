from click import Context

from ouranos.main import main
from ouranos.sdk.tests.plugin import dummy_plugin


class TestRootCommand:
    def test_get_command_plugin(self):
        ctx = Context(main)

        assert main.get_command(ctx, dummy_plugin.name) is dummy_plugin.command

    def test_get_command_not_found(self):
        ctx = Context(main)

        assert main.get_command(ctx, "not_a_plugin") is None

    def test_list_commands(self):
        ctx = Context(main)

        assert dummy_plugin.name in main.list_commands(ctx)
