import os
import sys
import time

tparams = {
  "value": {
    "pin": "input",
    "dtype": "int"
  },
  "output": {
    "pin": "output",
    "dtype": "int"
  }
}

if __name__ == "__main__":
    dir_containing_seamless = os.path.normpath(
     os.path.join(os.path.dirname(__file__), '../../')
    )
    sys.path.append(dir_containing_seamless)

    from seamless import cell, pythoncell, transformer, context
    ctx = context()

    c_data = cell("int").set_context(ctx).set(4)
    c_output = cell("int").set_context(ctx)
    c_code = pythoncell().set_context(ctx)

    cont = transformer(tparams).set_context(ctx)
    c_data.connect(cont.value)

    c_code.connect(cont.code)
    c_code.set("return value*2")

    print(c_data.data, "'" + c_code.data + "'", c_output.data)
    cont.output.connect(c_output)

    time.sleep(0.001)
    # 1 ms is usually enough to print "8", try 0.0001 for a random chance
    print(c_data.data, "'" + c_code.data + "'", c_output.data)

    c_data.set(5)
    c_code.set("return value*3")

    c_output2 = cell("int")
    cont2 = transformer(tparams).set_context(ctx)
    c_code.connect(cont2.code)
    c_data.connect(cont2.value)
    cont2.output.connect(c_output2)

    # c_output3 = cell("int")
    # cont2.output.connect(c_output3)

    cont.destroy()
    # this will sync the controller I/O threads before killing them
    cont2.destroy()
    # this will sync the controller I/O threads before killing them
    print(c_data.data, "'" + c_code.data + "'", c_output.data)
    print(c_output2.data)
