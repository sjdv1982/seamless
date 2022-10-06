# Macros and the low level

***IMPORTANT: This documentation section is a stub.***

The function of the low level is threefold:

- First, the low level is another way to use Seamless, using `seamless.core` instead of `seamless.highlevel`. In general, the low-level is a simplified version of the high level. All transformers are in Python, all cells are simple cells (you *can* use structured cells but their syntax is cumbersome), there is no translation, you can never delete cells or anything else, and everything (pins, celltypes) has to declared in advance.

- Second, the low level is more powerful than the high level.

    1. The low level has *reactors*, which function as transformers except that 1) they maintain state between invocations; and 2) they can edit the values some of their (independent!) input pins ("edit pins"). Since in Seamless, there is no history and modification of (independent) values creates a new workflow, the low-level allows self-editing workflows. In the future, reactors may be ported to the high level.

    2. The low level has *macros*. Macros have input pins, and whenever any input changes, the macro code is executed. ***Macro code is Python code that uses the low level, constructing a low-level context***. This context can be connected to the main context that contains the macro. Macros can be nested indefinitely. Macros allow Seamless to overcome the limitations of directed acyclic graphs, by allowing cyclic dependencies (nested macros where the nesting terminates based on the value of the macro input pin), if statements (building a connection or not, based on the value of the macro input pin) and for loops (building cells and connections for each value of the macro input pin). Macros are exposed to the high level as `seamless.highlevel.Macro`, although the macro code itself must fundamentally contain low level code. High-level contexts graphs can be embedded in the low level using seamless.core.HighLevelContext.

- Finally, the low level is how the high level is implemented in Seamless. The translation of a high level context graph is one big macro: whenever translation is triggered, Seamless enters macro mode and builds a low-level context based on the value of the high-level context graph, destroying any previous low-level context. This is typically one-to-many: for example, a high-level compiled transformer is translated into several low-level transformers.

Relevant tests:

- macro-simple.py, macro.py, macro-elision.py
- the high-in-low tests
- all low-level tests

<!--
### D8. The low level

Intermediate:
- High-level Macros
- Rules for the low level
- low-level macros
- macro mode
- reactors and editpins
- high-in-low: 
    - HighLevelContext (link to: how the high level wraps the graph data structure)
    - pseudo-connections; 

In-depth:
- Libraries vs macros

Async tasks overview
-->