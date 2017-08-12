from __future__ import print_function
import sys
from lxml import etree, objectify

def main():
    xml = objectify.parse(open(sys.argv[1]))
    print(etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode())
