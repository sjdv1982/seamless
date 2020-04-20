from seamless.highlevel import Context, Cell
import seamless

ctx = Context()

def serve(filename, sharename=None, mount=False):
    import os
    cell = Cell()
    cell.celltype = "text"
    _, ext = os.path.splitext(filename)
    cell.mimetype = ext[1:]
    if mount:
        cell.mount(filename, mode="rw", authority="file")
    else:
        data = open(filename, "rb").read()
        cell.set(data)
    if sharename is None:
      sharename = filename
    cell.share(path=sharename, readonly=True)
    return cell

ctx.files = Context()
f = ctx.files
f.html = serve("grid-editor.html", mount=True)
f.css = serve("grid-editor.css", mount=True)
f.js = serve("grid-editor.js", mount=True)
f.jslib = serve("grid-editor-lib.js")
import os
seamless_dir = os.path.dirname(seamless.__file__)
clientfile = seamless_dir + "/js/seamless-client.js"
f.seamless_client_js = serve(clientfile, sharename="seamless-client.js")
ctx.translate()

params1 = {
  "square_size": 40,
  "offset_x": 30,
  "offset_y": 200,
}

params2 = {
  "square_size": 40,
  "offset_x": 300,
  "offset_y": 200,
}

params3 = {
  "square_size": 40,
  "offset_x": 750,
  "offset_y": 200,
}

params4 = {
  "square_size": 40,
  "offset_x": 750,
  "offset_y": 200,
}

edit_params1 = {
  "step1": 1,
  "step2": 1,
  "max1": 1,
  "max2": 1,
}

edit_params2 = {
  "step1": 0,
  "step2": 2,
  "max1": 0,
  "max2": 2,
}

ctx.grid_params = {
    "grid_params": [params1, params2, params3, params4],
    "edit_params": [edit_params1, edit_params2]
}
ctx.grid_params.celltype = "plain"
ctx.grid_params.mount("grid_params.json", authority="file")

ctx.translation_ = [1, -1]
ctx.translation_.celltype = "plain"
ctx.translation_.mount("translation.json")

def combine_grid_params(grid_params, translation):  
  result = grid_params.unsilk  
  p = result["grid_params"][3]
  p["trans_x"] = translation.unsilk[0]
  p["trans_y"] = translation.unsilk[1]
  return result

ctx.combine_grid_params = combine_grid_params
ctx.combine_grid_params.grid_params = ctx.grid_params
ctx.combine_grid_params.translation = ctx.translation_

ctx.combined_grid_params = ctx.combine_grid_params

ctx.grid_data1 = """
 00 10 10 10 00
 10 11 01 11 10
 00 10 10 10 00
"""

ctx.grid_data2 = """
 00 00 02 00 00
 00 02 02 02 02
 00 00 02 02 00
"""

ctx.grid_data1.celltype = "text"
ctx.grid_data1.mount("grid_data1.txt", authority="file")
ctx.grid_data1.share(readonly=False)

ctx.grid_data2.celltype = "text"
ctx.grid_data2.mount("grid_data2.txt", authority="file")
ctx.grid_data2.share(readonly=False)

ctx.combined_grid_params.celltype = "plain"
ctx.combined_grid_params.share()
ctx.translation_.share("translation", readonly=False)
ctx.translate()
ctx.compute()

ctx.save_graph("grid-editor.seamless")
ctx.save_zip("grid-editor.zip")

print("If this script is run with IPython, open http://localhost:5813/ctx/grid-editor.html")