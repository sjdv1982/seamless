#seamless.raedae.py
def namespacehandler(...):
    ...
def metaschemahandler(...):
    ...
def schemahandler(...):
    ...
def leafhandler(...):
  ...
default_registry = {
  "namespace": namespacehandler,
  "expr": expr_handler, #for custom (Python) terms in RAE expression
  "schema": schemahandler,
  "metaschema": metaschemahandler,
  "leaf": leafhandler,
}

#seamless.__init__.py
seamless.systems._add("raedae", seamless.raedae.default_registry)

#seamless.lightweight.handlers.py
def vertexformat_schema_handler(...):
    ...
    return {
      "schema": ...
    }

def shader_handler(...):
    ...

def primbucketeer(...):
    #receives *all* instances of the primitive
    #no more @parent references, although buffer references still exist
    bufferbucket = {
      "buffer_descriptor": {},
      "bucket": {}
    }
    ...
    return bufferbucket

def primitive_schema_handler(primschema):
    ...
    return {
      "schema": {
        "dtype": <primschema> dtype,
        "virtual_base": "primitive",
        "namespace": "primitives",
        "_value": {
            "command": <primschema>,
            "shader": <primschema>,
        }
        "indices": {
          "dtype": "int",
          "dims": 1,
        },
        "vertices" : {
          "dtype": <primschema> vertexformat,
          "dims": 1,
        },
      }
      "leaf": {
        "dtype": <primschema> dtype,
        "handler": primbucketeer,
      },
    }
#seamless.lightweight.expr.py
def get_matrix(...):
    ...

@macro(registrar="raedae.lightweight")
def setup():
    return [

      "namespace":
        "names": ["vertexformats", "shaders", "primitives", "scenenodes"],
        ...
      },

      "expr": {
        "get_matrix": seamless.lightweight.expr.get_matrix,
      },

      "schema": {
        "name": "quaternion",
        "schema": {
          "x": "float32",
          "y": "float32",
          "z": "float32",
          "w": "float32",
        }
      },

      "schema": {
        "name": "vec3",
        "schema": {
          "x": "float32",
          "y": "float32",
          "z": "float32",
        }
      },

      "schema": {
        "name": "mat3",
        "schema": {
          "x": "vec3",
          "y": "vec3",
          "z": "vec3",
        }
      },

      "schema": {
        "name": "matrix",
        "schema": {
          "position": "vec3",
          "orientation": "quaternion | mat3",
          "scale": "vec3",
        }
        "default": {
          "position": (0,0,0),
          "orientation": (0,0,0,1),
          "scale": (1,1,1),
        }
      },

      "schema": {
        "dtype": "shader",
        "namespace": "shaders",
        "handler": shader_handler,
        "schema": {
          #code, but also if it uses the modelview,camera,_position/_orientation
          # from the parent (normal/billboard)
          #and support for multiple shader codes
          #and for vertex/fragment/geometry? code
        }
      }

      "metaschema": {
        "metadtype": "vertexformat",
        "handler": vertexformat_schema_handler,
      },

      "metaschema": {
        "metadtype": "primitive_schema",
        "handler": primitive_schema_handler,
        "schema" : {
          "command": seamless.raedae.enum("triangles", "lines", ...),
          "shader": "shader",
          "vertices" : {
            "metatype": "vertexformat",
            "metanamespace": "vertexformats",
            "dims": 1,
          },
        },
      },

      "schema" : {
        "dtype": "scenenode",
        #no handler: auto-breakdown to primitive leaves
        "schema": {
          "matrix": "matrix",
          "_matrix": "@get_matrix(SELF._matrix, PARENT._matrix)",
          "children": {
            "dtype": "scenenode | primitive", #recursive definition
            "dims": 1,
            "indexed": 1, #so that PARENT will point to the parent of the children array,
            # not to the children array itself,
            # and INDEX will refer to the index in PARENT.children
          }
        },
        "partial": {
          #support for partials:
          #the namespace where to store them
          "namespace": "scenenodes",
        }
      },
    ]

@macro(registrar="raedae.lightweight")
def setup_color():
    [
      "schema": {
        "dtype": "colored_scenenode",
        "base": "scenenode",
        "schema": {
          "color": {
            "dtype": "vec3",
            "default": "@parent.color"
            "default2": (1,1,1)
          },
        }
      },
      "schema": {
        "dtype": "colored_vertexformat",
        "base": "vertexformat",
        "schema": {
          #indices gets automatically added
          #coordinates gets automatically added
          "color": "vec3" #automatically expanded into 1D array,
          # automatically changed into "colors"
          #automatically checked that all arrays have the same length
        },

      "schema": {
        "dtype": "colored_primitive",
        "base": "primitive",
        "schema": {
          "command": "triangles",
          "shader": ...,
          "vertices": "!vertexformats::colored_vertexformat",
        }

    ]

#seamless.lightweight.splitter.py

@macro
def splitter(bufferbuckets):
    ret = {"buffer":{}, "buckets":{}}
    ...
    return ret


#seamless.lightweight.render.py
@macro(system="raedae.lightweight")
def render(ctx, scene):
    import seamless.raedae
    proc, cells = ctx.processes, ctx.cells
    t = proc.transform( seamless.raedae.transform() )
    t.input.cell().set(scene)
    s = proc.splitter( seamless.lightweight.splitter() )
    t.output.cell().connect(s.input)
    b = cells.bufferdict().set(s.output.buffer) #live macro
    r = proc.renderer( seamless.lightweight.vispy_renderer() )
    b.connect(r.bufferdict)
    s.output.buckets.connect(r.buckets)
    ctx.define_pins(b)


#main script

scene = {
  "dtype": "scenenode",
  "value": {
    "children": [
      {
        "dtype": "colored_primitive",
        "value": {
          "colors": [[1,0,0],[0,1,0],[0,0,1]],
          "coordinates": "$triangles"
        }
      },
      {
        "dtype": "colored_primitive",
        "value": {
          "colors": "$colors2",
          "coordinates": "$triangles2"
        }
      },

      {
        "dtype": "colored_scenenode",
        "value": {
          "color": [1,0,0],
          "children": [
            {
              "dtype": "colored_primitive",
              "value": {
                "colors": "@UNIFORM(PARENT.color)",
                "coordinates": [[1,2,3],[4,5,6], [7,8,9]]
              }
            }
          ]
        }
      }

    ]
  }
}

ctx = seamless.context()
proc, cells = ctx.processes, ctx.cells
scenecell = cells.scene(("json", "lightweight", "scene")).set(scene)
r = proc.render( seamless.lightweight.render(scenecell) ) #live macro
triangles = r.triangles.cell() #numpy array, dtype = float32, shape = (3,3)
triangles2 = r.triangles2.cell() #ERROR: first dimension unknown
ar = np.array([[11,12,13], [14,15,16], [17,18,19], [20,21,22]], dtype=triangles2.dtype)
cells.buffer.triangles2().set(ar).connect(r.triangles2) #shape is now known: (4,3)
colors2 = r.colors2.cell() #numpy array, dtype = float32, shape = (4,3)
colors2.set((0,0,1)) #all 4 triangles2 are now blue
