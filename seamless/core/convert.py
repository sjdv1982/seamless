"""
Note that all routines use buffer_cache.

try_convert/try_conversion may return:
  True (trivial success)
  A checksum (success)
  -1 (future success)
  None (future success or failure)
  False (unconditional failure),

## Strategy for try_convert, sync:

Conversion is checksum + source_celltype + target_celltype => checksum .
optional arguments: buffer, buffer_info
flag: values_as_false: 

1. Convert conversion to a chain of conversions. Iterate over each. 
First don't pass on buffer and set values_as_false (to quickly find undoable chains); 
  if None or -1, re-run with the buffer and values_as_false to the original
2. If buffer_info present:
     Run convert_with_buffer_info and set result. If not None/-1, return result.
   Else:
     Check for:
      - trivial conversion (return True)
      - values (return None, or False if values_as_false)
      - reinterpret/possible (set result to None)
      - reformat (set result to -1)
      - forbidden conversion (return False)
3. 
If buffer present:
    - Evaluate converter using buffer, return result.
Else:
    - return None

## Strategy for try_conversion, async:
Conversion is checksum + source_celltype + target_celltype => checksum .
extra arguments: cachemanager, database

flag: failure_as_exception, buffer_local, buffer_remote 

1. Convert conversion to a chain of async conversions. Run each using an async construct 
that runs in parallel and terminates on first exception
First unset buffer_local and buffer_remote, and set failure_as_exception (to quickly find undoable chains); 
  if None or -1, re-run with buffer_local set to the original, and set failure_as_exception to True.
  if None or -1, re-rerun with all arguments set to the original.
2.
    Check for:
    - trivial conversion (return True)
    - values (return None, or, if not buffer_local/_remote: False, or exception if false_as_exception)
    - reinterpret/possible (set result to None)
    - reformat (set result to -1)
    - forbidden conversion (return False, or exception if false_as_exception)
3. Obtain buffer_info locally or remotely.
   Run convert_with_buffer_info and set result. If not None/-1, return result.
   If False, raise exception if false_as_exception
4. If not buffer_local, return result.
   Else, try to obtain buffer using local cache, evaluate converter using buffer, return result.
5. If not buffer_remote, return result.
   Else, try to obtain buffer remotely, evaluate converter using buffer, return result.

## do_convert, do_conversion
Will either return a checksum (success) or None (failure)
For async: extra arguments: cachemanager, database

Will do try_conversion, and if that fails with None or -1, do an value conversion.
Value conversion will use sync/async versions of (de)serialize and calculate_checksum,
(instead of the Tasks in the value conversion in evaluate_expression.py)


"""