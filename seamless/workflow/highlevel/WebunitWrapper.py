from weakref import ref
from copy import deepcopy


class WebunitWrapper:
    def __init__(self, ctx):
        self._ctx = ref(ctx)

    def _get_webunits(self):
        return self._ctx()._graph.params.get("webunits", {})

    def __getattr__(self, attr):
        webunits = self._get_webunits()
        if attr not in webunits:
            raise AttributeError(attr)
        return WebunitSubWrapper(self._ctx(), attr)

    def __dir__(self):
        return sorted(list(self._get_webunits().keys()))

    def __str__(self):
        return str(self._get_webunits())

    def __repr__(self):
        return str(self)


class WebunitSubWrapper:
    def __init__(self, ctx, webunit_type: str):
        self._ctx = ref(ctx)
        self._webunit_type = webunit_type

    def _get_sub_webunits(self):
        webunits = self._ctx()._graph.params.get("webunits", {})
        sub_webunits = webunits.get(self._webunit_type, [])
        return sub_webunits

    def _get_sub_webunits_dict(self):
        sub_webunits = self._get_sub_webunits()
        sub_webunits_dict = {}
        for itemnr, item in enumerate(sub_webunits):
            sub_webunits_dict[item["id"]] = itemnr, item
        return sub_webunits_dict

    def __getattr__(self, attr):
        sub_webunits_dict = self._get_sub_webunits_dict()
        if attr not in sub_webunits_dict:
            raise AttributeError(attr)
        _, item = sub_webunits_dict[attr]
        return deepcopy(item)

    def __delattr__(self, attr):
        sub_webunits_dict = self._get_sub_webunits_dict()
        if attr not in sub_webunits_dict:
            raise AttributeError(attr)
        pos, _ = sub_webunits_dict[attr]
        sub_webunits = self._get_sub_webunits()
        sub_webunits.pop(pos)

    def __dir__(self):
        return sorted(list(self._get_sub_webunits_dict().keys()))

    def __str__(self):
        sub_webunits = self._get_sub_webunits()
        return str({item["id"]: item for item in sub_webunits})

    def __repr__(self):
        return str(self)
