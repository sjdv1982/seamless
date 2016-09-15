from abc import ABC, abstractmethod

from .process import Process, InputPin, OutputPin


class MappedPinProcess(Process, ABC):
    """Process with mapped pins to attribute names"""

    def __init__(self, params):
        self.output_names = []
        self._name_to_dtype = {}
        self._name_to_pin = {}
        self._io_attrs = []

        self._initialise()

        for name in params:
            param = params[name]

            if param["pin"] == "input":
                index = len(self._name_to_dtype)
                pin = self._create_input_pin(name, param["dtype"])
                self._name_to_dtype[name] = param["dtype"]

            else:
                assert param["pin"] == "output"
                index = len(self.output_names)
                pin = self._create_output_pin(name, param["dtype"])
                self.output_names.append(name)

            self._io_attrs.append(name)
            self._name_to_pin[name] = pin

    @abstractmethod
    def _initialise(self):
        pass

    def _create_input_pin(self, name, dtype):
        return InputPin(self, name, dtype)

    def _create_output_pin(self, name, dtype):
        return OutputPin(self, name, dtype)

    def set_context(self, context):
        super(self, MappedPinProcess).set_context(context)

        for pin in self._name_to_pin.values():
            pin.set_context(context)

        return self

    def __getattr__(self, name):
        try:
            return self._name_to_pin[name]

        except KeyError:
            raise AttributeError(name)
