"""Imperative transformations"""

class Transformation:
    """Imperative transformations can be queried for their .value
or .logs. Doing so forces their execution.
As of Seamless 0.11, forcing one transformation also forces 
    all other transformations."""

    def __init__(self):
        self._value = None
        self._logs = None

    def _set(self, value, logs):
        self._value = value
        self._logs = logs

    @property
    def value(self):
        from . import _wait
        if self._value is None:
            _wait()
        return self._value

    @property
    def logs(self):
        from . import _wait
        if self._value is None:
            _wait()
        return self._logs
