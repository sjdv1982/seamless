from lxml import etree
from collections import OrderedDict


def xmlschemaparse(string):
    if isinstance(string, str):
        string = string.encode('UTF8')
    return etree.fromstring(string)


def get_blocks(schema):
    ret = OrderedDict()
    classes = schema.findall("silk")
    for c in classes:
        typename = c.attrib["typename"]
        cc = {}
        ret[typename] = cc
        cc["methodblocks"] = []
        for block in c.findall("methodblock"):
            cc["methodblocks"].append(block.text)
        cc["formblocks"] = []
        for block in c.findall("formblock"):
            cc["formblocks"].append(block.text)
        cc["validationblocks"] = []
        for blocknr, block in enumerate(c.findall("validationblock")):
            b = {"name": str(blocknr+1), "text": block.text}
            cc["validationblocks"].append(b)
        cc["errorblocks"] = []
        for block in c.findall("errorblock"):
            errors = []
            for error in block.findall("error"):
                code = error.find("code").text
                message = error.find("message").text
                errors.append({"code": code, "message": message})
            cc["errorblocks"].append(errors)
    return ret

def get_init_tree(schema):
    ret = OrderedDict()
    classes = schema.findall("silk")
    for c in classes:
        typename = c.attrib["typename"]
        cc = {}
        ret[typename] = cc
        for member in c.findall("member"):
            name = member.find("name")
            init = member.find("init")
            if init is not None:
                cc[name.text] = init.text
        if not len(cc):
            ret[typename] = None
    return ret
