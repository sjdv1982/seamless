Status: {
  "result": "undefined",
  "tf": "error"
}

**************************************************
* STDOUT:                                        *
**************************************************
TEST
**************************************************

Traceback (most recent call last):
  File "/seamless/seamless/core/execute.py", line 87, in _execute
    exec_code(code, identifier, namespace, inputs, output_name)
  File "/seamless/seamless/core/cached_compile.py", line 58, in exec_code
    exec(code_obj, namespace)
  File "Seamless transformer: .tf", line 1, in <module>
    print('TEST'); raise Exception(a)
Exception: 1

