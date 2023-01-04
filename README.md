# Seamless: a cell-based interactive workflow framework

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/sjdv1982/seamless-binder-demo/main?labpath=basic-example.ipynb)

Seamless is a framework to set up reproducible workflows and computations that respond to changes in cells. Cells define the input data as well as the source code of the computations. All cells and computations can be created, edited and connected interactively.

The main application domains are data science, scientific computing, software prototyping, and interactive web services.

Workflows, computations and results are all internally represented as trees of checksums. This makes them strongly interoperable and reproducible.

## Features

Seamless workflows define both data and code in a single file. Any user can re-execute a Seamless workflow (reproducing its results) and then modify it easily: by editing workflow parameters in a web interface, or by changing the source code cells, or by extending the workflow with additional steps. Modification of the workflow takes place while it is running.

Seamless-generated web interfaces are interactive and collaborative for the user. Also, the process of workflow creation is interactive for the programmer. At all times, the status of all of the workflow is being reported.
In fact, there is no sharp distinction between user and programmer. Each step of the workflow (which can be in Python, bash, C/C++, or several other languages) can be mounted to a file, so that you can use Git, diff, and text editors. If you use an IDE, live debugging with code breakpoints is supported. As a programmer, you can work collaboratively, creating a live shared session where a team of developers can work on different parts of the workflow in parallel.

### Source code: <https://github.com/sjdv1982/seamless>

### Documentation: <http://sjdv1982.github.io/seamless>

## Try out Seamless

You can try out Seamless in your browser, without any installation, thanks to the Binder project. Click on the badge below:

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/sjdv1982/seamless-binder-demo/main?labpath=basic-example.ipynb)

## Quick installation

First, [install Docker](https://docs.docker.com/get-docker/)
and [miniconda](https://docs.conda.io/en/latest/miniconda.html).

```bash
docker pull rpbs/seamless
conda create -n seamless -c rpbs -c conda-forge seamless-cli -y
conda activate seamless
```

For more details, see [Installation](https://github.com/sjdv1982/seamless/blob/master/installation.md)

## Basic example

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
ctx.c = ctx.add.result  # ctx.c => Seamless cell
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
ctx.a.mount("a.json")
ctx.b.celltype = "plain"
ctx.b.mount("b.json")
ctx.c.celltype = "plain"
ctx.c.mount("c.json", mode="w")
ctx.add.code.mount("code.py")
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

##### Source code

<https://github.com/sjdv1982/seamless>

##### Documentation

<http://sjdv1982.github.io/seamless>
