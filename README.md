Seamless: a cell-based reactive programming framework
=====================================================

Seamless is a framework to set up protocols (workflows) and computations that respond to changes in cells. Cells define the input data as well as the source code of the computations, and all cells can be edited interactively.

The main application domains are scientific computing, scientific web services, data visualization, and interactive development of algorithms.

Protocols, computations and results are all represented as directed acyclic graphs that consist of cell checksums. This makes them strongly interoperable and reproducible. Unlike other workflow systems, Seamless graphs are self-contained and do not depend on the content of external files, URLs, identifiers, version numbers, or other kinds of metadata.

### Documentation: <http://sjdv1982.github.io/seamless>


Installation
============

Seamless is meant to run from inside a Docker container.

First, you must [install Docker](https://docs.docker.com/get-docker/)
and [(mini)conda](https://docs.conda.io/en/latest/miniconda.html).

Then, installation is as follows:

```
# Pull docker image
docker pull rpbs/seamless

# Install Seamless command line tools
conda install -c rpbs seamless-cli
```

### Getting started

The command ```seamless-ipython``` launches an IPython terminal inside a
Seamless Docker container.

```seamless-jupyter``` does the same for Jupyter Notebook.


### Installation under conda

conda create -n seamless
conda activate seamless
conda install 'python==3.7.3' pip
pip install -r https://raw.githubusercontent.com/sjdv1982/seamless/experimental/requirements.txt
pip install -r https://raw.githubusercontent.com/sjdv1982/seamless/experimental/requirements-extra.txt
conda install -c rpbs silk seamless-framework

Basic example
=============

First, start **IPython** (`seamless-ipython`) or **Jupyter** (`seamless-jupyter` => create a new Python Notebook).

#### 1. Import Seamless in IPython or Jupyter
```python
from seamless.highlevel import Context
ctx = Context()
```

#### 2. Set up a simple Seamless context

```python
def add(a, b):
    return a + b

ctx.a = 10              # ctx.a => Seamless cell
ctx.b = 20              # ctx.b => Seamless cell
ctx.add = add           # ctx.add => Seamless transformer
ctx.add.a = ctx.a
ctx.add.b = ctx.b
ctx.c = ctx.add         # ctx.c => Seamless cell
await ctx.computation() # in a .py file, use "ctx.compute()" instead
ctx.c.value
```

```Out[1]: <Silk: 30 >```

```python
ctx.a += 5
await ctx.computation()
ctx.c.value
```

```Out[2]: <Silk: 35 >```

#### 3. Define schemas and validation rules
```python
ctx.add.example.a = 0.0  # declares that add.a must be a number
ctx.add.example.b = 0.0

def validate(self):
    assert self.a < self.b

ctx.add.add_validator(validate, name="validate")

await ctx.computation()
print(ctx.add.exception)
# Validation passes => exception is None
```

#### 4. Create an API for a Seamless cell
```python
def report(self):
    value = self.unsilk
    if value is None:
        print("Sorry, there is no result")
    else:
        print("The result is: {}".format(value))

ctx.c.example.report = report
await ctx.computation()
ctx.c.value.report()
```
```Out[3]: The result is 35```

#### 5. Mount cells to the file system
```python
ctx.a.celltype = "plain"
ctx.a.mount("/tmp/a.txt")
ctx.b.celltype = "plain"
ctx.b.mount("/tmp/b.txt")
ctx.c.celltype = "plain"
ctx.c.mount("/tmp/c.txt", mode="w")
ctx.add.code.mount("/tmp/code.py")
await ctx.translation()
```

#### 6. Share a cell over HTTP

``` python
ctx.c.mimetype = "text"
ctx.c.share()
await ctx.translation()
```
```bash
>>> curl http://localhost:5813/ctx/c
35
```


#### 7. Control cells from Jupyter
```python
from ipywidgets import IntSlider, IntText

a = IntSlider(min=-10,max=30)
b = IntSlider(min=-10,max=30)
c = ctx.c.output()
ctx.a.traitlet().link(a)
ctx.b.traitlet().link(b)
display(a)
display(b)
display(c)
```

```Out[4]```

<details><summary>Jupyter widgets (shown only on github.io, not on github.com)</summary>
<!-- Load require.js. Delete this if your page already loads require.js -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.4/require.min.js" integrity="sha256-Ae2Vz/4ePdIu6ZyI/5ZGsYnb+m0JlOmKPjt6XZ9JJkA=" crossorigin="anonymous"></script>
<script src="https://unpkg.com/@jupyter-widgets/html-manager@*/dist/embed-amd.js" crossorigin="anonymous"></script>
<script type="application/vnd.jupyter.widget-state+json">
{
    "version_major": 2,
    "version_minor": 0,
    "state": {
        "9a30009f9d044d0184b9ae4611b41440": {
            "model_name": "LayoutModel",
            "model_module": "@jupyter-widgets/base",
            "model_module_version": "1.2.0",
            "state": {}
        },
        "7a3a04d1e170466086ce2f1cc7ff8206": {
            "model_name": "SliderStyleModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "description_width": ""
            }
        },
        "b71e9f617e4c4447962aa02e83fff9b3": {
            "model_name": "IntSliderModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "layout": "IPY_MODEL_9a30009f9d044d0184b9ae4611b41440",
                "max": 30,
                "min": -10,
                "style": "IPY_MODEL_7a3a04d1e170466086ce2f1cc7ff8206",
                "value": 15
            }
        },
        "9df6e150ff994aa8b67c891d4db6e638": {
            "model_name": "LayoutModel",
            "model_module": "@jupyter-widgets/base",
            "model_module_version": "1.2.0",
            "state": {}
        },
        "d5ad72717ba74f13884773a12b3d504e": {
            "model_name": "SliderStyleModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "description_width": ""
            }
        },
        "510c3503bf774d09a065c977fb395bd0": {
            "model_name": "IntSliderModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "layout": "IPY_MODEL_9df6e150ff994aa8b67c891d4db6e638",
                "max": 30,
                "min": -10,
                "style": "IPY_MODEL_d5ad72717ba74f13884773a12b3d504e",
                "value": 20
            }
        },
        "a16e33985975424f8471454796384dc7": {
            "model_name": "LayoutModel",
            "model_module": "@jupyter-widgets/base",
            "model_module_version": "1.2.0",
            "state": {}
        },
        "9ac3e0bde75e42ef885d3beb5852d878": {
            "model_name": "OutputModel",
            "model_module": "@jupyter-widgets/output",
            "model_module_version": "1.0.0",
            "state": {
                "layout": "IPY_MODEL_a16e33985975424f8471454796384dc7",
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "text/plain": "35"
                        },
                        "metadata": {}
                    }
                ]
            }
        },
        "29241e1f7b1a49ffabfd90b27805f7bf": {
            "model_name": "LayoutModel",
            "model_module": "@jupyter-widgets/base",
            "model_module_version": "1.2.0",
            "state": {}
        },
        "7e22056badc243caa0bb61361d96025b": {
            "model_name": "SliderStyleModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "description_width": ""
            }
        },
        "f4ac183f4141492c8004ffee95e19b9a": {
            "model_name": "IntSliderModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "layout": "IPY_MODEL_29241e1f7b1a49ffabfd90b27805f7bf",
                "max": 30,
                "min": -10,
                "style": "IPY_MODEL_7e22056badc243caa0bb61361d96025b",
                "value": 15
            }
        },
        "ecb30d47382442dc8d8d494d6ce7a799": {
            "model_name": "LayoutModel",
            "model_module": "@jupyter-widgets/base",
            "model_module_version": "1.2.0",
            "state": {}
        },
        "584cda9e4c6046358fadb8a24dc2e94d": {
            "model_name": "SliderStyleModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "description_width": ""
            }
        },
        "f876716b1ad643d48baefadc4a669afa": {
            "model_name": "IntSliderModel",
            "model_module": "@jupyter-widgets/controls",
            "model_module_version": "1.5.0",
            "state": {
                "layout": "IPY_MODEL_ecb30d47382442dc8d8d494d6ce7a799",
                "max": 30,
                "min": -10,
                "style": "IPY_MODEL_584cda9e4c6046358fadb8a24dc2e94d",
                "value": 20
            }
        },
        "c5f3f3ba20054786a97cfb016dc64016": {
            "model_name": "LayoutModel",
            "model_module": "@jupyter-widgets/base",
            "model_module_version": "1.2.0",
            "state": {}
        },
        "dc3ebd64e9fb40bc9fd964e7292ed326": {
            "model_name": "OutputModel",
            "model_module": "@jupyter-widgets/output",
            "model_module_version": "1.0.0",
            "state": {
                "layout": "IPY_MODEL_c5f3f3ba20054786a97cfb016dc64016",
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "text/plain": "35"
                        },
                        "metadata": {}
                    }
                ]
            }
        }
    }
}
</script>

<script type="application/vnd.jupyter.widget-view+json">
{
    "version_major": 2,
    "version_minor": 0,
    "model_id": "f4ac183f4141492c8004ffee95e19b9a"
}
</script>

<script type="application/vnd.jupyter.widget-view+json">
{
    "version_major": 2,
    "version_minor": 0,
    "model_id": "f876716b1ad643d48baefadc4a669afa"
}
</script>

<script type="application/vnd.jupyter.widget-view+json">
{
    "version_major": 2,
    "version_minor": 0,
    "model_id": "dc3ebd64e9fb40bc9fd964e7292ed326"
}
</script>
</details>


#### 8. Save the entire state of the context
```python
# Graph and checksums, as JSON
ctx.save_graph("basic-example.seamless")
# Checksum-to-buffer cache, as ZIP file
ctx.save_zip("basic-example.zip")
```

#### 9. In a new notebook / IPython console:
```python
from seamless.highlevel import load_graph
ctx = load_graph(
    "basic-example.seamless",
    zip="basic-example.zip"
)
await ctx.computation()
ctx.c.value
```
```Out[1]: <Silk: 35 >```
```python
ctx.add.code.value
```
```Out[2]: 'def add(a, b):\n    return a + b'```
```bash
>>> curl http://localhost:5813/ctx/c
35
```


## Additional features
- Transformers can be written in Python, IPython, bash, or any compiled language (C, C++, ...).
- Bash transformers can be executed inside Docker images.
- IPython transformers can use IPython magics, allowing the use of languages such as Cython (tested), Matlab/Octave (untested), Julia (untested), or R (untested).
- The use of Redis as a checksum-to-buffer cache
- Seamless instances can communicate, serving as job slaves or result caches for transformations.
- Interactive monitoring of status and exception messages.

More examples
=============
<https://github.com/sjdv1982/seamless/tree/master/examples>

<https://github.com/sjdv1982/seamless/tree/master/tests/highlevel>
