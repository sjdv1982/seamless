class HelpMixin:
    @property
    def help(self):
        from .Help import HelpCell

        path = self._path
        if path is not None and path[:1] == ("HELP",):
            raise AttributeError("Help cells can't have help")
        return HelpCell(self)

    @help.setter
    def help(self, value):
        from .Help import HelpCell

        wrapper = HelpCell(self)
        return wrapper.set(value)

    def __getattribute__(self, name: str):
        if name == "__dict__":
            return super().__getattribute__(name)
        elif name == "__doc__":
            return self.self.help.value
        elif name in self.__dict__:
            return self.__dict__[name]
        return super().__getattribute__(name)
