import jinja2

params = PINS.DYNAMIC_HTML_PARAMS.get()
tmpl = PINS.DYNAMIC_HTML_TEMPLATE.get()
vars_ = []
vars_full = []
for var_name, v in params["vars"].items():
    vv = v[0]
    vars_.append(vv)
    chars = ".[]{}"
    full_var = True
    for char in chars:
        if char in vv:
            full_var = False
            break
    if full_var:
        vars_full.append(vv)
dynamic_html0 = jinja2.Template(tmpl).render(
    {"vars": vars_, "vars_full": vars_full}
)

from seamless.websocketserver import websocketserver
websocketserver.start() #no-op if the websocketserver has already started

dynamic_html = jinja2.Template(dynamic_html0).render({
    "IDENTIFIER": IDENTIFIER,
    "socket": websocketserver.socket,
})
PINS.dynamic_html.set(dynamic_html)

def update(on_start):
    do_evals = set()
    for var_name in params["vars"]:
        pin = getattr(PINS, var_name)
        if not pin.updated:
            continue
        value = pin.get()
        var, evals = params["vars"][var_name]
        msg = {"type":"var", "var": var, "value": value}
        #print("MSG", msg, IDENTIFIER)
        websocketserver.send_message(IDENTIFIER, msg)
        for e in evals:
            do_evals.add(e)
    for html_name in params["html"]:
        pin = getattr(PINS, html_name)
        if not pin.updated:
            continue
        value = pin.get()
        id_ = params["html"][html_name]
        msg = {"type":"html", "id": id_, "value": value}
        #print("MSG", msg, IDENTIFIER)
        websocketserver.send_message(IDENTIFIER, msg)
    for e in params["evals"]:
        do_eval = False
        do_on_start = params["evals"][e]
        if on_start:
            if do_on_start == True:
                do_eval = True
            elif do_on_start == False:
                do_eval = False
            else:
                do_eval = (e in do_evals)
        else:
            do_eval = (e in do_evals)
        if do_eval:
            pin = getattr(PINS, e)
            value = pin.get()
            msg = {"type":"eval", "value": value}
            #print("MSG", msg, IDENTIFIER)
            websocketserver.send_message(IDENTIFIER, msg)

update(on_start=True)
