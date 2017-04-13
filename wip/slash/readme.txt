Bash replacement

take-home message:
- Caching is absolutely unnecessary for seamless; just create more cells!
- You DO want "caching" (well, dependency tracking) when a macro context is
 recreated; you may want to keep (copy/move over) cell contents and worker state
- Two dialects:
    slash-0
  - has static and dynamic variables
  - has no cell expressions, only cell names => no dynamic cells
  - has cell lists and variable lists, but only static-length

 lib.slash.slash1.script
 lib.slash.slash1.multi_script
 lib.slash.slash0.script
 lib.slash.slash0.multi_script
 lib.slash.slash0.command
 aux functions:
 - register a normal worker as slash command


Standard syntax:
<command> <arguments> > <cell name or cell expression>

Arguments can be: cells, variable expressions or literals

Variable: same as bash variable

Variable expression: mix of $variable and literals.

Dynamic variable: variable whose *value* is defined by the content of a cell,
i.e. only known at runtime. Since for-loops are always unrolled, for-loop
variables are *not* dynamic variables.

Dynamic variable expression: variable expression that contain dynamic variables
Cell expression: either the name of a cell, or a non-dynamic variable expression

Dynamic cell: cell whose *name* is defined by a dynamic variable expression,
i.e. only known at runtime. Cells whose names are defined by a non-dynamic
variable expression are *not* dynamic cells.

Variable list: variable that consists of multiple variables. A variable list
is static if all of its variables are static, otherwise it is dynamic.
A variable list is can be static-length or dynamic-length.
Can be iterated over in for loops, but only if static-length.
[0], [1], [-1] gets the first/second/last variable, this is only allowed if
the variable list is static-length.

Subcontexts: contains other cells.
"foo/bar" gets static cell "bar" from a subcontext "foo", this is only allowed
if the subcontext is static
"bar" can also be a static cell expression
"bar" can also be a dynamic cell expression, in which case the result is a
dynamic cell.

command lookup:
    foo looks in registered slash commands, then on disk using "which"
    /foo looks on disk, absolute path
    ./foo looks on disk, in cwd
    $DIR/foo looks in os.environ["DIR"]
argument lookup:
   STDIN, STDOUT, STDERR are substituted
   -bar: literal
   2: literal
   "bar", 'bar': literal
   bar looks for cell "bar"
   if bar contains $ outside quotes, then it is a variable expression
    $foo: looks for variable "foo"
    $foo-2: looks for variable "foo" and appends the literal "-2"
|, 2> bar, 2>&1 bar: as expected
!> bar: captures all files created by the command into a dynamic
subcontext "bar".

foo = bar: defines a variable "foo" from variable expression "bar".
If the variable expression is dynamic, then "foo" will be a dynamic variable.

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
static cell "foo" (or "bar"). Just cell names, no expressions.
Slash-1 and slash-0

@macro_var foo [bar]: defines a str macro parameter "foo" that becomes a
static variable "foo" (or "bar")
Only slash-1; substitution in slash-0

@macro_list foo [bar]: defines a JSON macro parameter "foo" that becomes a
static-length static variable list "foo" (or "bar")
Only slash-1; substitution in slash-0

@macro_context foo [bar]: defines a JSON macro parameter "foo" that becomes a
static subcontext "foo" (or "bar")
Only slash-1; substitution in slash-0

@export foo [bar]: exports a cell(/variable/variable list/subcontext) "foo" as
text(/str/JSON/JSON) output pin [under the name "bar"].
If "foo" is a variable list, the JSON will contain a list
If it is a subcontext, the JSON will contain a dict
Slash-1 and slash-0

@cat foo bar ... > baz
defines a variable list "baz" from variable expressions foo, bar, etc.
If all variable expressions are static, "baz" will be static,
else it will be dynamic.
If a variable expression corresponds to $(name-of-variable-list-foobar) then
the result will be flattened. If "foobar" is dynamic-length, then "baz" will be
dynamic-length.
Under all other circumstances, "baz" will be static-length.
Slash-1 and slash-0

@load foo bar: loads a dynamic variable "foo" from the contents of cell "bar".
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
Slash-1 and slash-0

@cell foo bar: loads the content of variable expression "foo" as cell "bar".
If foo is a dynamic variable expression, then "bar" will be a dynamic cell.
Slash-1 and slash-0

@alias foo bar:
Substitution all instances of the text "foo" with "bar"
Slash-1 and slash-0, although slash-0 generated from slash-1 does not contain it

@load foo bar: loads file "foo" as cell "bar". "foo" can be a static variable
expression. "foo" is monitored continuously.
Slash-1 and slash-0

@globload foo bar: loads all files corresponding to glob pattern "foo" as
dynamic subcontext "bar". To generate cell names, everything before the first *
or ? is eliminated, and slashes afterwards are replaced by "-".
Only slash-1

@mount foo bar:
Mount all files in static subcontext "foo" onto the file system. File names
generated as cell names, subcontexts become subdirectories.
Slash-1 and slash-0

@subcontext foo:
Declares a subcontext "foo"
Only in slash-0; in slash-1 it is inferred from the code.

@cell_array foo bar:
Declare a cell array "foo" of length "bar".
Only slash-0, in slash-1 all cell arrays are in loops.

You can assign to every cell only once.

For loop syntax (only slash-1):
for i in foo; do
 ...
done
OR:
for i in foo > bar; do
  ...
done
OR:
for i in foo > bar, baz, ... ; do
  ...
done
OR:
for i,j in foo, foobaz; do
  ...
done
OR:
for i,j in foo, foobaz > bar, baz, ...; do
  ...
done

foo must be a variable NAME (no expression, no dollars!) of a static-length
 variable list. Same for foobaz.
bar will be created as static-length variable list with the same length as foo.
The loop has to assign to "bar" exactly once. If this is done with a static
variable expression, then bar will be static, else dynamic.

cell:: Marks a cell expression, which otherwise would be understood as variable
 expression

#####################################
EXAMPLE
#####################################

script1:
@input_cell pdb
$ATTRACTTOOLS/splitmodel pdb "model" > NULL !> pdbsplit
@export pdbsplit

script2:
@macro_context pdbsplit
@input_var atom1
@macro_var atom2
@glob pdbsplit x
@alias currpdb cell::pdbsplit/$xx #cannot use @cell since the name changes!
for xx in x > a,b,c-$atom2; do
  grep 'ATOM' currpdb | awk '{print $2}' > $xx/ind
  grep 'CA' currpdb | head -20 > a
  grep $atom1 currpdb > b
  grep $atom2 currpdb > c-$atom2
done
@cat a b > ab
@export ab
@export c-$atom2

slash-0:
script1: unchanged

script2:
@input_var atom1
@subcontext pdbsplit
@macro_cell pdbsplit/model-1
@macro_cell pdbsplit/model-2
@macro_cell pdbsplit/model-3
@subcontext model-1
@subcontext model-2
@subcontext model-3
@cell_array a 3
@cell_array b 3
@cell_array c-CB 3
@cell_array ab 6
grep 'ATOM' pdbsplit/model-1 | awk '{print $2}' > model-1/ind
grep 'CA' pdbsplit/model-1 | head -20 > a[0]
grep $atom1 pdbsplit/model-1 > b[0]
grep CB pdbsplit/model-1 > c-CB[0]
grep 'ATOM' pdbsplit/model-2 | awk '{print $2}' > model-2/ind
grep 'CA' pdbsplit/model-2 | head -20 > a[1]
grep $atom1 pdbsplit/model-2 > b[1]
grep CB pdbsplit/model-2 > c-CB[1]
grep 'ATOM' pdbsplit/model-3 | awk '{print $2}' > model-3/ind
grep 'CA' pdbsplit/model-3 | head -20 > a[2]
grep $atom1 pdbsplit/model-3 > b[2]
grep CB pdbsplit/model-3 > c-CB[2]
@cat a b > ab
@export ab
@export c-CB


#####################################
ALTERNATIVE EXAMPLE (more bash style, copy files in and out of the context)
#####################################
script1:
@load ~/data/complex.pdb pdb
$ATTRACTTOOLS/splitmodel pdb "model" > NULL !> pdbsplit
@export pdbsplit

script2:
@macro_context pdbsplit
@glob pdbsplit x
atom1=N
atom2=CB
@alias currpdb cell::pdbsplit/$xx #cannot use @cell since the name changes!
for xx in x; do
  grep ATOM currpdb | awk '{print $2}' > $xx/ind
  grep CA currpdb | head -20 > $xx/CA
  grep $atom1 currpdb > $xx/ATOM1
  grep $atom2 currpdb > $xx/$atom2
done
@mount . ~/splitpdb  #. means "all". Write to disk, but never read!

#results are now in:
# ~/splitpdb/$xx/ind
# ~/splitpdb/$xx/CA
# ~/splitpdb/$xx/ATOM1
# ~/splitpdb/$xx/CB

=>
script1: unchanged

script2:
@subcontext pdbsplit
@macro_cell pdbsplit/model-1
@macro_cell pdbsplit/model-2
@macro_cell pdbsplit/model-3
@subcontext model-1
@subcontext model-2
@subcontext model-3
grep 'ATOM' pdbsplit/model-1 | awk '{print $2}' > model-1/ind
grep 'CA' pdbsplit/model-1 | head -20 > model-1/CA
grep 'N' pdbsplit/model-1 > model-1/ATOM1
grep CB pdbsplit/model-1 > model-1/CB
grep 'ATOM' pdbsplit/model-2 | awk '{print $2}' > model-2/ind
grep 'CA' pdbsplit/model-2 | head -20 > model-3/CA
grep $atom1 pdbsplit/model-2 > model-2/ATOM1
grep CB pdbsplit/model-2 > model-2/CB
grep 'ATOM' pdbsplit/model-3 | awk '{print $2}' > model-3/ind
grep 'CA' pdbsplit/model-3 | head -20 > model-3/CA
grep 'N' pdbsplit/model-3 > model-3/ATOM1
grep CB pdbsplit/model-3 > model-3/CB
@mount . ~/splitpdb



Slash0 parsing:
Check for """, ''' => "Not supported" message
Split into lines and strip each line
Check for \ on the end of a line => "Not supported" message
Check for unmatched ' or " on each line => Syntax error
Identify and mask out '...', "..."
Parse @ separately, eliminate
Split every line into sublines using ; (not |)
Split the sublines into words
Check that no word is "&&" => "Not supported" message
Categorize words into >-like and non->-like
Every >-like must be followed by at least one non->-like
Every subline must contain at least one >-like
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
Compile to slash0


Look up all commands
Generate command strings and their arg lists.
Integrate with @, generate pins
Build the context!
