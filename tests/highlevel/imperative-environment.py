import seamless
seamless.delegate()
from seamless.imperative import transformer
'''
# For code with an incompatible file name

from types import ModuleType
import sys
from seamless.core.cached_compile import cached_compile

testcode = ModuleType("testcode")
testcode.__path__ = []
codeobj = cached_compile(open("pytorch_test1.py").read(), "testcode")
exec(codeobj, testcode.__dict__)
sys.modules["testcode"] = testcode
#del testcode
#import testcode
'''
import pytorch_test1 as testcode

main = transformer(testcode.main)
main.environment.set_conda("pytorch-environment.yml")
result = main(datapoints=1900, iterations=1900, learning_rate=1e-3)
print(result)
result = main(datapoints=1901, iterations=1901, learning_rate=1e-3)
print(result)

import pytorch_test2 as testcode
main2 = transformer(testcode.main)
main2.environment.set_conda("pytorch-environment.yml")
result = main2(batch_size=64, epochs=11, learning_rate=1e-3)
print(result)