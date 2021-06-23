import os, tempfile
from seamless.highlevel import Context, Cell

ctx = Context()
ctx.transform = lambda a,b: a + b
ctx.transform.a = 2
ctx.transform.b = 3
ctx.translate()
ctx.transform.example.a = 0
ctx.transform.example.b = 0
ctx.result = ctx.transform
ctx.result.celltype = "plain"
ctx.compute()
print(ctx.result.value)

print("")
print("ERROR 1:")
print("")

ctx.transform.language = "cpp"
ctx.code = ctx.transform.code.pull()
ctx.code = """
#include <iostream>
using namespace std;
extern "C" int transform(int a, int b, double *result) {
    cout << "transform " << a << " " << b << endl;
    return 1;
}"""
ctx.translate()
ctx.transform.result.example = 0.0 #example, just to fill the schema
ctx.transform.main_module.link_options = ["-lstdc++"]
ctx.compute()
print(ctx.transform.exception)
print("")
print("ERROR 2:")
print("")


ctx.code = """
#include <iostream>
using namespace std;
extern "C" int transform(int a, int b, double *result) {
    cout << "NOT PRINTED ";
    exit(1);
}"""
ctx.translate()
ctx.transform.result.example = 0.0 #example, just to fill the schema
ctx.compute()
print(ctx.transform.exception)
