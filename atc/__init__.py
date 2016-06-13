"""
ATC (Acquisition Through Conversion) manager
...
ATC conversion/invocation requests get expanded into an ATC chain

we can also process ATC chains directly

The ATC manager has the following associated feedback channels, disabled by default

If enabled, the channels report to the default sfport (seamless feedback port),

ATC converters, and therefore ATC chains, may have multiple inputs or outputs
However, every type of input may be consumed only once
  and if it is generated more than once, it may never be consumed

See the Spyder ATC chain for an example

"""



class ATCType(object):
    name = None
    converters = None
    methods = None

def init():
    pass
