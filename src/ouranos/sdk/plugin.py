from click import Command, Group


class Plugin:
    def __init__(self, name: str, main: Command):
        self.name = name
        self.main = main

    def register_command(self, cli_group: Group):
        cli_group.add_command(self.main, self.name)
