import os
import sys

dir_containing_seamless = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.append(dir_containing_seamless)

import seamless
seamless.init()

xml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '../spyder/example/coordinate.spyderschema.xml'))

with open(xml_path) as f:
    xml = f.read().encode('utf-8')

result = seamless.spyder.transform.schema2json(xml)
print(result)
