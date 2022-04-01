print("BLAH")
print(__file__)
print(__package__)
import sys, os
mod = sys.modules[__package__]
print(mod.__file__, os.path.dirname(mod.__file__))

import seamless.core.build_module
print(seamless.core.build_module.bootstrap())