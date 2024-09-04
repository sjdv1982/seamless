from seamless.workflow import Context, Cell

ctx = Context()
ctx.txt = "not OK"
ctx.txt.celltype = "text"
ctx.txt.mount("mount.txt", authority="file")
ctx.compute()
print(ctx.txt.value)

ctx.intcell = 780
ctx.intcell.celltype = "int"
ctx.intcell.mount("/tmp/intcell.txt")

ctx.cpp_cell = """
#include <iostream>
using namespace std;
int main() 
{
    cout << "Hello, World!";
    return 0;
}
"""
ctx.cpp_cell.celltype = "code"
ctx.cpp_cell.language = "cpp"
ctx.cpp_cell.mount("/tmp/cpp_cell.cpp")

ctx.txt2 = Cell()
ctx.txt2.celltype = "text"
ctx.link(ctx.txt2, ctx.txt)

ctx.compute()
# continue in interactive mode...
