class ModuleBase:
    MODULE_NAME = ""
    PROTOCOL = None
    INTERFACE = None
    COMMANDS = ()

    def commands(self):
        return list(self.COMMANDS)

    def run(self, command, **kwargs):
        if command not in self.COMMANDS:
            raise ValueError("unsupported command: %s" % command)
        method = getattr(self, command, None)
        if method is None or command.startswith("_"):
            raise AttributeError("command method not found: %s" % command)
        return method(**kwargs)

    def execute(self, command, **kwargs):
        return self.run(command, **kwargs)

    def setup(self, **_config):
        return self.info()

    def self_test(self):
        return {"ok": True}

    def info(self):
        data = {
            "name": self.MODULE_NAME,
            "commands": self.commands(),
        }
        if self.PROTOCOL:
            data["protocol"] = self.PROTOCOL
        if self.INTERFACE:
            data["interface"] = self.INTERFACE
        details = self.details()
        if details:
            data.update(details)
        return data

    def details(self):
        return {}
