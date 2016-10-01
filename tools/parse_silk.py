from __future__ import print_function
import sys
from seamless.silk.typeparse import parse
from lxml import etree

silktext = open(sys.argv[1]).read()
tree = parse(silktext)
print(etree.tostring(
    tree,
    pretty_print=True,
    xml_declaration=True,
    encoding="UTF-8").decode()
)
