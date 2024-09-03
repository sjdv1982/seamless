def convert_checksum_dict(checksum_dict, prefix):
    """
    Convert highlevel checksum dict keys to checksum dict keys that a structured cell expects
    """
    result = {}
    for k in checksum_dict:
        if k == "schema":
            result[k] = checksum_dict[k]
            continue
        if not k.startswith(prefix):
            continue
        k2 = "value" if k == prefix else k[len(prefix + "_") :]
        if (
            k2 == "auth"
            and checksum_dict[k]
            == "d0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c"
        ):  # {}
            continue
        result[k2] = checksum_dict[k]
    return result
