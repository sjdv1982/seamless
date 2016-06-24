import seamless
seamless.init()

from seamless.cell import cell, pythoncell

c_data = cell("int", 4)
c_output = cell("int")
c_code = pythoncell()
print(c_data, c_output, c_code)
