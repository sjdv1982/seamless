from __future__ import print_function
import sys
from seamless.silk.parse import parse
from lxml import etree

silktext = open(sys.argv[1]).read()
silkdict = parse(silktext)
first = True
for k, v in spydict.items():
    if not first:
        print("")
    print(etree.tostring(
        v,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8").decode()
    )
