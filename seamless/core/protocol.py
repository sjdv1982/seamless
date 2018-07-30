def set_cell(cell, value, *,
  default, from_buffer, force
):
    mode = "buffer" if from_buffer else "ref"
    different, text_different = cell.deserialize(value, mode, None,
      from_pin=False, default=default,force=force
    )
    return different, text_different
