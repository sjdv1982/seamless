import jinja2, jinja2.meta
import json

env = {}
depsgraph = {}
templates = []
jenv = jinja2.Environment()

class Node:
    _ignore_deps = ["range"]
    def __init__(self, name):
        self.name = name
        self.template = None
        self.template_code = None
        self.up_to_date = False
        self.template_deps = []
        self.env_deps = []
        self.dependees = []

    def render(self, visited=None):
        if self.up_to_date:
            return env[self.name]

        if self.template is None:
            raise RuntimeError("Cannot render template '{0}'" % self.name)
        if visited is None:
            visited = []
        if self.name in visited:
            cycle = visited[visited.index(self.name):] + [self.name]
            raise RuntimeError("Cyclic template dependency: {0}".format(cycle))
        visited.append(self.name)

        for dep in sorted(self.template_deps):
            #print("DEP", self.name, dep)
            depsgraph[dep].render(visited)
        result = self.template.render(env)
        self.up_to_date = True
        #print("RENDER", self.name)
        env[self.name] = result
        return result

    def set_dirty(self):
        self.up_to_date = False
        for dependee in self.dependees:
            depsgraph[dependee].set_dirty()

    def set_template(self, template_code):
        if template_code == self.template_code:
            return
        self.template_code = template_code
        self.template = None
        self.set_dirty()
        ast = jenv.parse(template_code)
        deps = jinja2.meta.find_undeclared_variables(ast)
        new_env_deps = []
        new_template_deps = []
        for d in sorted(deps):
            if d in env:
                new_env_deps.append(d)
            elif d in templates:
                new_template_deps.append(d)
            elif d in self._ignore_deps:
                continue
            else:
                raise RuntimeError("Unknown dependency: '{0}'".format(d))
        self.template = jinja2.Template(ast)
        for dep in self.template_deps + self.env_deps:
            depsgraph[dep].dependees.remove(self.name)
        self.env_deps = new_env_deps
        self.template_deps = new_template_deps
        for dep in self.template_deps  + self.env_deps:
            depsgraph[dep].dependees.append(self.name)

def make_template():
    global result_template
    import jinja2
    tempdef = PINS.TEMPLATE_DEFINITION.get()
    if PINS.TEMPLATE_DEFINITION.updated:
        env.clear()
        depsgraph.clear()
        templates[:] = tempdef["templates"]
        result_template = tempdef.get("result", None)
        if len(templates) > 1:
            assert result_template is not None
        else:
            result_template = templates[0]
        assert result_template in templates, (result_template, templates)

    tempdef = PINS.TEMPLATE_DEFINITION.get()
    environment = tempdef["environment"]

    env_updates = list()
    for k, v in environment.items():
        inp = getattr(PINS, k)
        if inp.updated or k not in env:
            val = inp.get()
            if isinstance(val, (bytes, str)):
                sval = val
            else:
                sval = json.dumps(val, indent=2)
            env[k] = sval
            env_updates.append(k)

    for k in env_updates:
        if k not in depsgraph:
            node = Node(k)
            node.up_to_date = True
            depsgraph[k] = node
        for nodename in depsgraph[k].dependees:
            depsgraph[nodename].set_dirty()

    templ_updates = []
    for t in templates:
        template = getattr(PINS, t)
        if template.updated or t not in depsgraph:
            if t not in depsgraph:
                node = Node(t)
                depsgraph[t] = node
            templ_updates.append(t)
    for t in templ_updates:
        template = getattr(PINS, t)
        node = depsgraph[t]
        node.set_template(template.get())

    firstnode = depsgraph[result_template]
    result = firstnode.render()

    PINS.RESULT.set(result)
