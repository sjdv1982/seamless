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
    from seamless import cell, pythoncell, transformer, context
    ctx = context()

    ctx.c_data = cell("int").set(4)
    ctx.c_output = cell("int")
    ctx.c_code = pythoncell()

    ctx.cont = transformer(tparams)
    ctx.c_data.connect(ctx.cont.value)


    ctx.c_code.connect(ctx.cont.code)
    ctx.c_code.set("return value*2")

    print(ctx.c_data.data, "'" + ctx.c_code.data + "'", ctx.c_output.data)
    ctx.cont.output.connect(ctx.c_output)

    ctx.equilibrate()
    print(ctx.c_data.data, "'" + ctx.c_code.data + "'", ctx.c_output.data)

    ctx.c_data.set(5)
    ctx.c_code.set("return value*3")

    ctx.c_output2 = cell("int")
    ctx.cont2 = transformer(tparams)
    ctx.c_code.connect(ctx.cont2.code)
    ctx.c_data.connect(ctx.cont2.value)
    ctx.cont2.output.connect(ctx.c_output2)

    # ctx.c_output3 = cell("int")
    # ctx.cont2.output.connect(ctx.c_output3)

    del ctx.cont
    # this will sync the controller I/O threads before killing them
    del ctx.cont2
    # this will sync the controller I/O threads before killing them
    print(ctx.c_data.data, "'" + ctx.c_code.data + "'", ctx.c_output.data)
    print(ctx.c_output2.data)
