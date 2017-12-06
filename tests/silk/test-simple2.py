from silk import Silk

s = Silk().set( [] )
s.append(1)
s.append(2)
print("VALUE: ", s)
#s.append(3.0)   # Error
def v(self): assert self > 0
s.add_validator(v, 0)   #  add a validator to v[0] => to all items
s.append(10)
s.append(0)   # Error
