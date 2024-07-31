import seamless
seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
ctx.a = {}
ctx.translate()
ctx.a.x = 20
def validate(self):
    print("VALIDATE", self)
    assert self.x > 0
ctx.a.schema.add_validator(validate, "validate")
ctx.compute()
print(ctx.a.value)
print(ctx.a.buffered)
print(ctx.a.exception)
print()

def validate(self):
    print("VALIDATE2", self)
    assert self.x > 100
ctx.a.schema.add_validator(validate, "validate")
ctx.compute()
print(ctx.a.value)
print(ctx.a.buffered)
print(ctx.a.exception)
print()

ctx.a.example.x = {}
print(ctx.a.schema)
print()
ctx.compute()
print(ctx.a.value)
print(ctx.a.buffered)
print(ctx.a.exception)
