Status: {
  "result": "undefined",
  "tf": "error"
}
seamless.core.transformation.SeamlessTransformationError: Traceback (most recent call last):
  File "/seamless/seamless/core/execute.py", line 85, in _execute
    exec_code(code, identifier, namespace, inputs, output_name)
  File "/seamless/seamless/core/cached_compile.py", line 58, in exec_code
    exec(code_obj, namespace)
  File "Seamless transformer: .tf", line 1, in <module>
    raise Exception(a)
Exception: 1


