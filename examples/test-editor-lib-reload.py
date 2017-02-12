import seamless
f = "test-editor-lib.seamless"
f2 = "test-editor-lib-reload.seamless"
ctx = seamless.fromfile(f)

import time
time.sleep(0.1)

ctx.tofile(f2, backup=False)

ctx.destroy() ##should not be necessary, but it is, for now (hard ref somewhere)
ctx = seamless.fromfile(f2)
time.sleep(0.1)
