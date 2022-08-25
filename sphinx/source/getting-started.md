# Getting started with Seamless

## Overview

Seamless is about reproducible, interactive workflows. This means that any user can re-execute a workflow (reproducing its results) and then modify it easily: by editing workflow parameters in a web interface, or by changing the source code, or by extending the workflow with additional steps, interoperating with new code. Modification of the workflow takes place while it is running. At all times, the status of the workflow is being reported. Thus, web interfaces are interactive for the user, and the process of workflow creation is interactive for the programmer. In fact, there is no sharp distinction between user and programmer. Each step of the workflow can be mounted to a file, so that you can use Git, diff, and text editors. If you use an IDE, live debugging with code breakpoints is supported. As a programmer, you decide what is the most urgent part of the workflow to work on, getting instant feedback, writing provisional code and parameters that can be improved and expanded later. If you choose, you can shift your focus to a web interface, visualization and validation, and then back to the main calculations, as you see fit. Or you can work collaboratively, creating a live shared session where a team of developers can work on different parts of the workflow in parallel.Seamless does impose some requirements on how you organize your code. Most of these requirements are common sense, and if you are experienced in writing code, you are probably following them already.

## Getting started

### For beginners

If the above overview makes you feel overwhelmed, please read the next chapter, the [beginner's guide](http://sjdv1982.github.io/seamless/sphinx/html/beginner.html). It explains basic concepts related to workflows and organizing your code in a clean and reproducible way. It also contains a series of Seamless guidelines for beginners.

### For experienced developers

If you are an experienced developer, you are strongly advised to read [Seamless explained](http://sjdv1982.github.io/seamless/sphinx/html/explained.html). It is easy to be confused when Seamless seems to work like something else that you already know, until it doesn't. One example: Seamless can give the illusion of being like Jupyter, but with non-linear execution and the ability to mount cells to the file system. Second example: Seamless can give the illusion of being like NextFlow, but based on values in memory instead of files, together with a reactive web interface. These illusions are on purpose, to make Seamless easier to learn, but under certain circumstances they break down. This is mostly because of checksums, which are used everywhere in Seamless.

## Moving forward

In the rest of this documentation, the features of Seamless are discussed. A decent knowledge of programming is assumed.

At the end, there is the documentation generated from the source code docstrings.

A final source of information are the examples and the tests. The feature documentation often refers to them.

### Running examples on BinderHub

Two of the examples can be run as notebooks on BinderHub, which means that no installation is necessary. The first is the [basic example](https://mybinder.org/v2/gh/sjdv1982/seamless-binder-demo/main?labpath=basic-example.ipynb).

The second is the [webserver demo](https://mybinder.org/v2/gh/sjdv1982/seamless-binder-demo/main?labpath=webserver.ipynb). This example shows how to port a simple data science notebook to a Seamless workflow with an interactive web interface.

### Running examples locally

Seamless has a series of examples. They have a README and one or more notebooks that you can run.

First you need to install Seamless (installation with Docker is assumed, followed by `conda activate seamless`).

Then, run `seamless-jupyter`.

Inside the Jupyter file tree, browse `seamless-examples`.
<https://github.com/sjdv1982/seamless/tree/master/examples>
and select the example you want to run. Then you can select the notebook that you want.

Two examples (the SnakeMake example and the grid editor example) do not contain notebooks, see their README for instructions.

### Running tests locally

Seamless comes with many tests, that also serve as a demonstration of a particular feature. You can see them in <https://github.com/sjdv1982/seamless/tree/master/tests/highlevel> . The "test-outputs" folder contains the expected output of the test.

To run test locally, run `seamless-jupyter-trusted` or `seamless-bash-trusted`. Inside the notebook file tree, browse `seamless-tests/highlevel`, or inside a command-line shell, go to `~/seamless-tests/highlevel`. Tests are typically executed with Python, see "test-list.txt" for details.

Finally, there are also low-level tests (`seamless-tests/lowlevel`), but these are not recommended for study.

<!--
## Additional features
- Transformers can be written in Python, IPython, bash, or any compiled language (C, C++, Rust, Go, ...).
- Bash transformers can be executed inside Docker images.
- IPython transformers can use IPython magics, allowing the use of languages such as Cython (tested), Matlab/Octave (untested), Julia (untested), or R (tested).
- The use of a database as a checksum-to-buffer cache
- Seamless instances can communicate, serving as job slaves or result caches for transformations.
- Interactive monitoring of status and exception messages.

Other workflow systems often require a certain amount of planning, or at least have a well-defined cycle of: modify workflow => run workflow => inspect workflow output.

In contrast, Seamless workflows are modified while they remain running, and they can be modified from multiple places: IPython/Jupyter, the file system, and/or a web interface.


However, if you are a beginner without much experience in programming or workflows,
the ability to edit everything at once may be quite overwhelming.




Stupid stuff...

Practical demo (webserver)
-->