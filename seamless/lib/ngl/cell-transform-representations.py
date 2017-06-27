molnames = PINS.molnames.get()
representations = PINS.representations.get()
assert isinstance(representations, list)
result = {molname:[] for molname in molnames}
for r in representations:
    assert isinstance(r, dict) #representations must be a list of dicts
    obj = molnames
    rr = r.copy()
    if "obj" in r:
        obj = r["obj"]
        if isinstance(obj, str):
            obj = [obj]
        rr.pop("obj")
    for molname in obj:
        result[molname].append(rr)

for molname in molnames:
    r = result[molname]
    pin = getattr(PINS, "representations_" + molname)
    pin.set(r)
