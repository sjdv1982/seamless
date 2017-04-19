Bash replacement

take-home message:
- Caching is absolutely unnecessary for seamless; just create more cells!
- You DO want "caching" (well, dependency tracking) when a macro context is
 recreated; you may want to keep (copy/move over) cell contents and worker state
- Two dialects:
    slash-0
  - has dynamic variables (static ones must be pre-substituted)
  - has no cell expressions, only cell names => no dynamic cells
  - has cell lists, but only static-length
  - has subcontexts
  - has dynamic-length variable lists.
    In both slash-0 and slash-1, they cannot be accessed (only exported)

 lib.slash.slash1.script
 lib.slash.slash1.multi_script
 lib.slash.slash0.script
 lib.slash.slash0.multi_script
 lib.slash.slash0.command
 aux functions:
 - register a normal worker as slash command


Glossary:

Arguments can be: cells, variable names, cell expressions or literals

Variable: same as bash variable

Variable expression: mix of $variable and literals.

Dynamic variable: variable whose *value* is defined by the content of a cell,
i.e. only known at runtime. Since for-loops are always unrolled, for-loop
variables are *not* dynamic variables.

Dynamic variable expression: variable expression that contain dynamic variables

Cell expression: the name of a cell, or a variable expression that
evaluates to the name of a cell. Dynamic variable expressions make the cell
expression dynamic.
Cell expressions are slash-1 only.

Dynamic cell: cell whose name is defined by a dynamic cell expression,
i.e. only known at runtime. Cells whose names are defined by a non-dynamic
variable expression are *not* dynamic cells.
Dynamic cells are slash-1 only.

Variable list: variable that consists of multiple variables. A variable list
is static if all of its variables are static, otherwise it is dynamic.
A variable list is can be static-length or dynamic-length.
Can be iterated over in for loops, but only if static-length.
[0], [1], [-1] gets the first/second/last variable, this is only allowed if
the variable list is static-length.

Subcontexts: contains other cells.
Subcontexts are static, coming from @macro_context (slash-1) or @subcontext
(slash-0)
Subcontexts can be used in cell expressions:
"foo/bar" gets static cell "bar" from a static subcontext "foo"
"bar" can also be a static cell expression
"bar" can also be a dynamic cell expression, in which case the result is a
dynamic cell.

*******
Standard command syntax:
<command name> <arguments> > <result> [&]
& means that the command does not take a seamless execution slot (TODO)

command name lookup:
    $FOO...: anything that starts with $-plus-all-capitals has BAR looked up in
     os.environ and the whole construct treated as a file name
    foo: looks in the following order:
      - an alias named "foo" (slash-1 only)
      - a register slash command named "foo" (TODO)
      - then on disk using "which"
    /foo looks on disk, absolute path
    ./foo looks on disk, in cwd
argument lookup:
   $BAR...: as $FOO... above
   -bar: literal
   2: literal
   "bar", 'bar': literal
   bar: looks for an alias called "bar".
    If none is found, slash doesn't know if a literal or a cell
    expression is meant, so an error is raised.
   $bar is a variable expression. It looks for the variable "bar" and
    substitutes its value
   $bar-1: looks for the variable "bar" and appends "-1".
    If bar="baz", $bar-1 will be "baz-1"

   !bar is a cell expression: It will evaluate "bar" as a literal or variable
    expression, and then look for a cell with that name.
    If bar="baz", !$bar will substitute (the file name of) the cell "baz"
      and !$bar-1 will substitute the cell "baz-1"
    "!" is also allowed (but not necessary) in other places where a cell
     expression is required, such as after ">" or in certain special commands.
    In slash-0, all cell expressions must be just cell names.
result lookup:
    Is a cell expression (see above), the ! is optional.
    In slash-0, all cell expressions must be just cell names.

|, 2> bar, 2>&1 bar: as expected
NULL is substituted with /dev/null, else stderr and stdout are printed on screen
!> bar: captures all files created by the command into a JSON cell "bar".
*******

foo = bar: defines a variable "foo" from variable expression "bar".
If the variable expression is dynamic, then "foo" will be a dynamic variable.
Slash-1 and slash-0. In slash-0, only if dynamic, and foo must have been
declared with @var.

@: special commands

@import_cell foo [bar]: defines a text input pin "foo" that becomes a
static cell "foo" (or "bar"). Just cell names, no expressions.
Slash-1 and slash-0

@import_var foo [bar]: defines an str input pin "foo" that becomes a
dynamic variable "foo" (or "bar"). Just variable names, no expressions.
Slash-1 and slash-0

@import_list foo [bar]: defines an JSON input pin "foo" that becomes a
dynamic-length dynamic variable list "foo" (or "bar").
Only slash-1

@macro_cell foo [bar]: defines a text macro parameter "foo" that becomes a
static, constant-value cell "foo" (or "bar"). Just cell names, no expressions.
Only slash-1; substitution in slash-0

@macro_var foo [bar]: defines a str macro parameter "foo" that becomes a
static variable "foo" (or "bar")
Only slash-1; substitution in slash-0

@macro_list foo [bar]: defines a JSON macro parameter "foo" that becomes a
static-length static variable list "foo" (or "bar")
Only slash-1; substitution in slash-0

@macro_context foo [bar]: defines a JSON macro parameter "foo" that becomes a
static subcontext "foo" (or "bar")
Only slash-1; substitution to "extern" in slash-0

@export foo [bar]: exports a cell (/JSON cell/variable/variable list/subcontext)
"foo" as text(/JSON/str/JSON/JSON) output pin [under the name "bar"].
Variables and variable lists are referred to as $foo.
If "foo" is a variable list, the JSON will contain a list
If it is a subcontext or JSON cell, the JSON will contain a dict
Slash-1 and slash-0

@cat foo bar ... > baz
defines a cell array "baz" from cell expressions foo, bar, etc.
If all cell expressions are static, "baz" will be static,
else it will be dynamic.
If a cell expression corresponds to $(name-of-cell-array-foobar) then
the result will be flattened. If "foobar" is dynamic-length, then "baz" will be
dynamic-length.
Under all other circumstances, "baz" will be static-length.
Slash-1 and slash-0

@read foo bar: loads a dynamic variable "foo" from the contents of cell "bar".
Slash-1 and slash-0

@lines foo bar: loads a dynamic-length dynamic variable list "foo" from the
contents of cell "bar". Every line of "bar" becomes an item in the list
Slash-1 and slash-0

@fields foo bar: loads a dynamic-length dynamic variable list "foo" from the
contents of cell "bar". Every field in every line of "bar" becomes an item
in the list.
Slash-1 and slash-0

@glob foo bar: loads all cell names in subcontext "foo" into
dynamic variable list "bar". If the subcontext is static, then
"bar" will be static-length, else dynamic-length.
Only slash-1

@cell foo bar: loads the content of variable expression "foo" as cell "bar".
If foo is a dynamic variable expression, then "bar" will be a dynamic cell.
Slash-1 and slash-0

@alias foo bar:
Substitution of all instances of the text "foo" with "bar"
There can't be any cell or subcontext called "foo" (declared using @cell,
@import_cell, @macro_cell, @load, @globload, @lines, @fields, @glob, @cat)
Slash-1 only, substituted in slash-0

@load foo bar: loads file "foo" as cell "bar". "foo" can be a static variable
expression. "foo" is monitored continuously.
Slash-1 and slash-0

@globload foo bar: loads all files corresponding to glob pattern "foo" as
dynamic subcontext "bar". To generate cell names, everything before the first *
or ? is eliminated, and slashes afterwards are replaced by "-".
The glob pattern is monitored.
Only slash-1

@map foo bar:
Map all files in "foo" onto the file system (write-only, no readback).
"foo" can be a cell, subcontext or JSON cell.
If "foo" is ".", the entire main context is mapped
File names are generated as cell names.
Subcontexts and JSON cells become subdirectories.
Slash-1 and slash-0

@subcontext foo:
Declares a subcontext "foo"
Only in slash-0; in slash-1 it is inferred from the code.

@cell_array foo bar:
Declare a cell array "foo" of length "bar".
Only slash-0, in slash-1 all cell arrays are in loops.

@var foo:
Declare a variable "foo" that will be assigned to in the script.
(using @read)
Only slash-0, in slash-1 it is inferred from code.

@var_list foo:
Declare a variable list "foo" that will be assigned to in the script.
(using @lines, @fields)
Only slash-0, in slash-1 it is inferred from code.

@intern foo:
Declare a cell "foo" that will be assigned to in the script.
Only slash-0, in slash-1 it is inferred from code.

@intern_json foo:
Declare a cell "foo" that will be assigned to in the script using !>
Will contain a JSON dict of captured file names and their contents
Only slash-0, in slash-1 it is inferred from code.

@extern foo:
Declare a cell "foo" that is supplied in the "extern" JSON argument of a slash-0
script.
Only slash-0, in slash-1 it is generated from @macro_context

You can assign to every cell only once.

For loop syntax (only slash-1):
for i in foo; do
 ...
done
OR:
for i in $foo > bar; do
  ...
done
OR:
for i in $foo > bar, baz, ... ; do
  ...
done
OR:
for i,j in $foo, $foobaz; do
  ...
done
OR:
for i,j in $foo, $foobaz > bar, baz, ...; do
  ...
done

foo must be a variable name of a static-length
 variable list. Same for foobaz.
bar will be created as static-length cell array with the same length as foo.
The loop has to assign to "bar" exactly once.

#####################################
EXAMPLE
#####################################

script1:
@input_cell pdb
$ATTRACTTOOLS/splitmodel !pdb "model" > NULL !> pdbsplit
@export pdbsplit

script2:
@macro_context pdbsplit
@input_var atom1
@macro_var atom2
@glob pdbsplit x
@alias currpdb !pdbsplit/$xx #cannot use @cell since the name changes!
for xx in $x > a,b,c-$atom2; do
  grep 'ATOM' currpdb | awk '{print $2}' > $xx/ind
  grep 'CA' currpdb | head -20 > a
  grep $atom1 currpdb > b
  grep $atom2 currpdb > c-$atom2
done
@cat a b > ab
@export ab
@export c-$atom2

slash-0:
script1: unchanged, except @intern_json pdbsplit, @cell pdb

script2:
@input_var atom1
@subcontext pdbsplit
@extern pdbsplit/model-1
@extern pdbsplit/model-2
@extern pdbsplit/model-3
@subcontext model-1
@intern model-1/ind
@subcontext model-2
@intern model-2/ind
@subcontext model-3
@intern model-3/ind
@cell_array a 3
@cell_array b 3
@cell_array c-CB 3
@cell_array ab 6
grep 'ATOM' !pdbsplit/model-1 | awk '{print $2}' > model-1/ind
grep 'CA' !pdbsplit/model-1 | head -20 > a[0]
grep $atom1 !pdbsplit/model-1 > b[0]
grep 'CB' !pdbsplit/model-1 > c-CB[0]
grep 'ATOM' !pdbsplit/model-2 | awk '{print $2}' > model-2/ind
grep 'CA' !pdbsplit/model-2 | head -20 > a[1]
grep $atom1 !pdbsplit/model-2 > b[1]
grep 'CB' !pdbsplit/model-2 > c-CB[1]
grep 'ATOM' !pdbsplit/model-3 | awk '{print $2}' > model-3/ind
grep 'CA' !pdbsplit/model-3 | head -20 > a[2]
grep $atom1 !pdbsplit/model-3 > b[2]
grep 'CB' !pdbsplit/model-3 > c-CB[2]
@cat a b > ab
@export ab
@export c-CB

#####################################
ALTERNATIVE EXAMPLE (more bash style, copy files in and out of the context)
#####################################
script1:
@load ~/data/complex.pdb pdb
$ATTRACTTOOLS/splitmodel !pdb "model" > NULL !> pdbsplit
@export pdbsplit

script2:
@macro_context pdbsplit
@glob pdbsplit x
atom1=N
atom2=CB
@alias currpdb !pdbsplit/$xx #cannot use @cell since the name changes!
for xx in $x; do
  grep ATOM currpdb | awk '{print $2}' > $xx/ind
  grep CA currpdb | head -20 > $xx/CA
  grep $atom1 currpdb > $xx/ATOM1
  grep $atom2 currpdb > $xx/$atom2
done
@map . ~/splitpdb  #. means "all". Write to disk, but never read!

#results are now in:
# ~/splitpdb/$xx/ind
# ~/splitpdb/$xx/CA
# ~/splitpdb/$xx/ATOM1
# ~/splitpdb/$xx/CB

=>
script1: unchanged, except @intern_json pdbsplit, @cell pdb

script2:
@subcontext pdbsplit
@extern pdbsplit/model-1
@extern pdbsplit/model-2
@extern pdbsplit/model-3
@subcontext model-1
@intern model-1/ind
@intern model-1/CA
@intern model-1/ATOM1
@subcontext model-2
@intern model-2/ind
@intern model-2/CA
@intern model-2/ATOM1
@subcontext model-3
@intern model-3/ind
@intern model-3/CA
@intern model-3/ATOM1
grep 'ATOM' pdbsplit/model-1 | awk '{print $2}' > model-1/ind
grep 'CA' pdbsplit/model-1 | head -20 > model-1/CA
grep 'N' pdbsplit/model-1 > model-1/ATOM1
grep 'CB' pdbsplit/model-1 > model-1/CB
grep 'ATOM' pdbsplit/model-2 | awk '{print $2}' > model-2/ind
grep 'CA' pdbsplit/model-2 | head -20 > model-3/CA
grep $atom1 pdbsplit/model-2 > model-2/ATOM1
grep 'CB' pdbsplit/model-2 > model-2/CB
grep 'ATOM' pdbsplit/model-3 | awk '{print $2}' > model-3/ind
grep 'CA' pdbsplit/model-3 | head -20 > model-3/CA
grep 'N' pdbsplit/model-3 > model-3/ATOM1
grep 'CB' pdbsplit/model-3 > model-3/CB
@map . ~/splitpdb



Slash-1 parsing:
Check for """, ''' => "Not supported" message
Split into lines and strip each line
Check for \ on the end of a line => "Not supported" message
Check for unmatched ' or " on each line => Syntax error
Identify and mask out '', ""
Parse @ separately, eliminate
Split every line into sublines using ; (not |)
Split the sublines into words
Check that no word is "&&" => "Not supported" message
Categorize words into >-like and non->-like
Every >-like must be followed by at least one non->-like
Every subline must contain at least one >-like
Categorize commands into command name, arguments and result
  Check the syntax for each.
Process all variable definitions:
  - Integrate with @
  - Evaluate all static ones
  - Account for all dynamic ones
  - Check that every variable is assigned only once, and never in a loop
Evaluate all cell expressions
  - Integrate with @
  - Unroll all loops
  - Check that there are no dynamic variable deps
  - Check that there are no duplicate definitions
  - Implicitly create subcontexts whose cells are created
Compile to slash-0

Slash-0 parsing:
Look up all commands
Generate command strings and their arg lists.
Integrate with @, generate pins
Build the context!
