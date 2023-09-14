import ruamel.yaml
yaml = ruamel.yaml.YAML(typ='safe')

def load(yamlfile):
    with open(yamlfile) as f:
        data = yaml.load(f)
    if not isinstance(data, dict):
        raise TypeError("Must be dict, not {}".format(type(data)))
    # TODO: validation!
    return data