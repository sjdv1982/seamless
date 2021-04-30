from seamless.highlevel import Context, Transformer, Cell

ctx = Context()

ctx.pdb0 = open("1crn.pdb").read()
ctx.pdb0.celltype = "text"
ctx.pdb0.share("pdb0.pdb", readonly=False)

ctx.filter_pdb = Transformer()
ctx.filter_pdb.language = "bash"
ctx.filter_pdb.code = 'grep ATOM pdb0 | awk \'$3 == "CA" || $3 == "C" || $3 == "O" || $3 == "N"\' > RESULT'
ctx.filter_pdb.pdb0 = ctx.pdb0

ctx.filtered_pdb = ctx.filter_pdb
ctx.filtered_pdb.celltype = "text"
ctx.filtered_pdb.share("filtered_pdb.pdb")

ctx.fix_pdb = Transformer()
ctx.fix_pdb.language = "bash"
ctx.fix_pdb.code = 'head -20 filtered_pdb > RESULT'
ctx.fix_pdb.filtered_pdb = ctx.filtered_pdb

ctx.pdb = ctx.fix_pdb
ctx.pdb.celltype = "text"
ctx.pdb.share("pdb.pdb")

ctx.filter_code >> ctx.filter_pdb.code
ctx.filter_code.share("filter_code.bash", readonly=False)
ctx.filter_code.mount("/tmp/filter_code.bash")

ctx.code >> ctx.fix_pdb.code
ctx.code.share("code.bash",readonly=False)
ctx.code.mount("/tmp/code.bash")

import seamless, os
seamless_dir = os.path.dirname(seamless.__file__)
c = ctx.js = Cell()
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share(path="seamless-client.js")

c = ctx.vismol_js = Cell()
c.celltype = "text"
c.mount("vismol.js", authority="file")
c.mimetype = "text/javascript"
c.share(path="vismol.js")

c = ctx.representation_js = Cell()
c.celltype = "text"
c.mount("pdb-representation.js", authority="file")
c.mimetype = "text/javascript"
c.share(path="representation.js", readonly=False)

c = ctx.html = Cell()
c.celltype = "text"
c.mount("share-pdb.html", authority="file")
c.mimetype = "text/html"
c.share(path="index.html")

ctx.compute()

ctx.save_graph("share-pdb.seamless")
ctx.save_zip("share-pdb.zip")

ctx.fix_pdb.language = "docker"
ctx.filter_pdb.language = "docker"
ctx.translate()

ctx.fix_pdb.docker_image = "ubuntu"
ctx.filter_pdb.docker_image = "ubuntu"
ctx.translate()

ctx.save_graph("share-pdb-docker.seamless")
ctx.save_zip("share-pdb-docker.zip")
