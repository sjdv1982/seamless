import numpy as np
import numexpr as ne
import pandas as pd
from pandas import DataFrame, eval as pd_eval
import seamless.pandeval
from seamless.pandeval.core.computation.eval import eval
# Sample data
s = np.zeros(6, 'S5')
v = np.array([5,8,3,6,7,2])
s[:4] = "Test", "Test2", "Test", "Test"
s_u = np.array([ss.decode() for ss in s])  # s as unicode
dic = {"s": s, "v": v}
dic_u = {"s": s_u, "v": v}


print("Golden standard (numexpr with ugly syntax)\t", ne.compute("(s == 'Test') & (v > 3)", dic))

df = DataFrame(dic)
print("pandas DataFrame with bytes (error)\t\t", df.eval("s == 'Test' and v > 3").values)
try:  # ugly syntax AND does not work
    print(df.eval("s == b'Test' and v > 3").values)
except AttributeError:
    print("*" * 50)
    import traceback; traceback.print_exc(0)
    print("*" * 50)

df_u = DataFrame(dic_u)
print("pandas DataFrame with unicode (works)\t\t", df_u.eval("s == 'Test' and v > 3").values)


print("pandas eval with bytes (wrong)\t\t\t", pd_eval("s == 'Test' and v > 3", global_dict=dic))
print("pandas eval with unicode (wrong)\t\t", pd_eval("s == 'Test' and v > 3", global_dict=dic_u))

print("pandeval eval with bytes (works)\t\t", eval("s == 'Test' and v > 3", global_dict=dic))
print("pandeval eval with unicode (works)\t\t", eval("s == 'Test' and v > 3", global_dict=dic_u))

dtype = np.dtype([("s", s.dtype), ("v", v.dtype)])
sv = np.zeros(len(s),dtype)
sv["s"] = s
sv["v"] = v

def struct_eval(expr, struct_array):
    global_dict = {k:struct_array[k] for k in struct_array.dtype.fields}
    return eval(expr, global_dict=global_dict)

print("struct_eval wrapper\t\t\t\t", struct_eval("s == 'Test' and v > 3", sv))
