default_policy = {
    "surplus_to_binary": "error",
    "accept_missing_binary_optional": True,
    "infer_property": True,
    "infer_item":  "uniform",
    "infer_type":  True,
    "infer_shapedarray":  True,
    "infer_dtype":  False,
    "infer_dtype_mixed":  False,
    "error_log": True,
    "infer_recursive":  False,
    "binary_validation": True,
    "infer_shape":  False,
    "re_infer_shape":  False,
}

#TODO: by default, if a property or item is a scalar,
#  Silk returns the naked scalar, not the Silk-wrapped scalar
# This can be turned off, or be made conditional on the presence of methods/validators
