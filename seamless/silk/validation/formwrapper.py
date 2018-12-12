class FormWrapper:
    """Wrapper around an object and its form (and storage)
    Unlike MixedObject, it does not store the path, but
     provides direct sub-object access"""

    _wrapped = None
    _form = None
    _storage = None

    def __init__(self, wrapped, form, storage):
        self._wrapped = wrapped
        self._form = form
        self._storage = storage

    def __contains__(self, item):
        return item in self._wrapped

    def __getattribute__(self, attribute):
        if attribute in ("_wrapped", "_form", "_storage") or attribute.startswith("__"):
            return super().__getattribute__(attribute)
        else:
            return getattr(self._wrapped, attribute)

    def __getitem__(self, item):
        subitem = self._wrapped[item]
        substorage = None
        subform = None
        form = self._form
        if form is not None:
            if isinstance(item, int):
                form_items = form.get("items")
                if isinstance(form_items, list):
                    try:
                        subform = form_items[item]
                    except IndexError:
                        pass
            else:
                if "properties" in form:
                    subform = form["properties"].get(item)
            if isinstance(subform, str):
                substorage = subform
                subform = None
            elif subform is None:
                pass
            else:
                substorage = subform.get("storage")
        if subform is None and substorage is None:
            return subitem
        else:
            return FormWrapper(subitem, subform, substorage)

    def __str__(self):
        return str(self._wrapped)

    def __repr__(self):
        return repr(self._wrapped)
