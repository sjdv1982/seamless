from seamless.silk import register
#for f in ("coordinate.silk", "vector.silk", "axissystem.silk", "attracteasymodel.silk"):
#TODO: resources
for f in ("coordinate.silk", "vector.silk", "axissystem.silk"):
    register(open("example/" + f).read())

from seamless.silk import Silk
c = Silk.Coordinate(1,2,3)
print(c)
