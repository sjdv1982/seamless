# Copyright 2016, Sjoerd de Vries
from ...exceptions import SilkSyntaxError

def macro_enum(name, content):
    if name != "Enum":
        return

    c = content.strip()
    lparen = c.find("(")
    if lparen == -1:
        raise SilkSyntaxError("'%s': missing ( in Enum" % content)
    rparen = c.rfind(")")
    if rparen == -1:
        raise SilkSyntaxError("'%s': missing ) in Enum" % content)
    enum = c[lparen+1:rparen]
    return "String " + c[:lparen] + c[rparen+1:] \
     + "\nenum {\n  " + enum + "\n}\n" \
