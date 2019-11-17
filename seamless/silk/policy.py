# TODO: many policies are not yet respected...

default_policy = {
    "accept_missing_binary_optional": True,
    "infer_default": False,
    "infer_new_property": True,
    "infer_object": False,
    "infer_new_item":  True,
    "infer_array": "auto",
    "infer_type":  True,
    "infer_storage":  True,
    "infer_ndim":  True,
    "infer_strides":  False,
    "infer_recursive":  False,
    "binary_validation": True,
    "infer_shape":  False,
    "re_infer_shape":  False,
    "infer_required": False,
    "wrap_scalar": False
}

no_infer_policy = {
    "accept_missing_binary_optional": True,
    "infer_default": False,
    "infer_new_property": False,
    "infer_object": False,
    "infer_new_item":  False,
    "infer_array": False,
    "infer_type":  False,
    "infer_storage":  False,
    "infer_ndim":  False,
    "infer_strides":  False,
    "infer_recursive":  False,
    "binary_validation": True,
    "infer_shape":  False,
    "re_infer_shape":  False,
    "infer_required": False,
    "wrap_scalar": False
}

#TODO: code facility to globally override default_policy
