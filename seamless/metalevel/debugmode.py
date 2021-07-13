"""
...
You can switch from direct_print to another mode, but not vice versa.
"""
print("TODO: refactor away all instances of DIRECT_PRINT; implement ide.debug_hook")
import weakref
import os

class ValidationError:
    pass

def validate_light_mode(transformer):
    raise ValidationError("TEST!")
    env = os.environ
    hostcwd = env.get("HOSTCWD")
    docker_image = env.get("DOCKER_IMAGE")
    #...

class DebugMode:
    def __init__(self, transformer):
        self._tf = weakref.ref(transformer)
        self._direct_print = False
        self._mode = None

    def activate(self, mode=None):
        if self._mode is not None:
            raise ValueError("Debug mode is already active.")

        if mode is not None:
            assert mode in ("full", "light"), mode
        else:
            try:
                validate_light_mode(self._tf())
            except ValidationError as exc:
                reason = exc.args[0]
                msg = """Cannot enter light debug mode. 
Reason: {}
Entering full debug mode."""
                print(msg.format(reason))
                mode = "full"

        if mode == "full":
            raise NotImplementedError
        elif mode == "light":
            raise NotImplementedError
        self._mode = mode

    @property
    def direct_print(self):
        """Causes the transformer to directly print any messages,
        instead of buffering them and storing them in Transformer.logs"""
        return self._direct_print

    @direct_print.setter
    def direct_print(self, value):
        if not isinstance(value, bool):
            raise TypeError(type(value))
        self._direct_print = value

    def _to_low_level(self):
        debug = {
            "direct_print": self._direct_print,
            "python_attach": False,
            "python_attach_message": None,
            "generic_attach": False,
            "generic_attach_message": None,
        }
        return debug
