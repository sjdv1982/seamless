from seamless.highlevel import Context
ctx = Context()
ctx.txt = "not OK"
ctx.txt.celltype = "text"
ctx.txt.mount("mount.txt", authority="file")
ctx.equilibrate()
print(ctx.txt.value)

ctx.mount("mount-test", persistent=False)
ctx.intcell = 780
ctx.intcell.celltype = "int"

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

ctx.equilibrate()
