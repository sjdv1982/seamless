class SchemaWrapper:
    def __init__(self, wrapped, schema_mounter):
        self._wrapped = wrapped
        self._schema_mounter = schema_mounter

    def __getattr__(self, attr):
        if attr in ("_wrapped", "_schema_mounter"):
            return object.__getattr__(self, attr)
        else:
            return getattr(self._wrapped, attr)

    def __setattr__(self, attr, value):
        if attr in ("_wrapped", "_schema_mounter"):
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

    def mount(self, path=None, mode="rw", authority="cell", persistent=True):
        return self._schema_mounter(
            path=path,
            mode=mode,
            authority=authority,
            persistent=persistent
        )
