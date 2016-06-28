from __future__ import print_function
import sys;
from seamless.spyder.parse import parse
from lxml import etree

spytext = open(sys.argv[1]).read()
spydict = parse(spytext)
first = True
for k, v in spydict.items():
    if not first: print("")
    print(etree.tostring(v, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode())
