import seamless, time
seamless.init()

from seamless.cell import cell, pythoncell

c_data = cell("int", 4)
c_output = cell("int")
c_code = pythoncell()

from seamless.controllers.ExampleTransformer import ExampleTransformer
cont = ExampleTransformer("int", "int")
c_data.connect(cont.input)
c_code.connect(cont.code)
c_code.set("return input*2")

print(c_data.data, "'"+c_code.data+"'", c_output.data)
cont.output.connect(c_output)

time.sleep(0.001)
#1 ms is usually enough to print "8", try 0.0001 for a random chance
print(c_data.data, "'"+c_code.data+"'", c_output.data)

c_data.set(5)
c_code.set("return input*3")
cont.destroy() #this will sync the controller I/O threads before killing them
print(c_data.data, "'"+c_code.data+"'", c_output.data)
