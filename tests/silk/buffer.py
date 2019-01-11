from seamless.silk import Silk

buf = {}
def validate(self):
    assert self.x > self.y

s = Silk(buffer=buf)
s.x = 10
s.y = 2
s.add_validator(validate)
print(s.schema)

s.y = 7.0
s.y = 200
print(s.data, buf)
s.x = 1000
print(s.data, buf)
