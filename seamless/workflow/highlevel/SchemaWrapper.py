from weakref import ref


class SchemaWrapper:
    def __init__(self, parent, wrapped, path):
        self._wrapped = wrapped
        assert path in ("SCHEMA", "RESULTSCHEMA")
        self._path = path
        self._parent = ref(parent)

    def mount(self, *args, **kwargs):
        raise Exception("Schema cells cannot be mounted. Use ctx.link instead")

    @property
    def _virtual_path(self):
        return self._parent()._path + (self._path,)

    def add_validator(self, validator, name):
        """Adds a validator function (in Python) to the schema.

        The validator must take a single argument, the (buffered) value of the cell
        It is expected to raise an exception (e.g. an AssertionError)
        if the value is invalid.

        If a previous validator with the same name exists,
        that validator is overwritten.
        """
        return self._parent().handle.add_validator(validator, name=name)

    def __getattr__(self, attr):
        if attr == "_wrapped":
            return object.__getattr__(self, attr)
        else:
            return getattr(self._wrapped, attr)

    def __setattr__(self, attr, value):
        if attr in ("_wrapped", "_parent", "_path"):
            object.__setattr__(self, attr, value)
        else:
            setattr(self._wrapped, attr, value)

    def __getitem__(self, item):
        return self._wrapped[item]

    def __setitem__(self, item, value):
        self._wrapped[item] = value

    def __dir__(self):
        return dir(self._wrapped)

    def __str__(self):
        return str(self._wrapped)

    def __repr__(self):
        return repr(self._wrapped)
