from seamless.highlevel import Context, Transformer

ctx = Context()

ctx.pdb0 = open("1crn.pdb").read()
ctx.pdb0.celltype = "text"
ctx.pdb0.share()

ctx.filter_pdb = Transformer()
ctx.filter_pdb.language = "bash"
ctx.filter_pdb.code = 'grep ATOM pdb0 | awk \'$3 == "CA" || $3 == "C" || $3 == "O" || $3 == "N"\' '
ctx.filter_pdb.pdb0 = ctx.pdb0

ctx.bb_pdb = ctx.filter_pdb
ctx.bb_pdb.celltype = "text"
ctx.bb_pdb.share()

ctx.bb_pdb = ctx.filter_pdb
ctx.bb_pdb.celltype = "text"
ctx.bb_pdb.share()

ctx.fix_pdb = Transformer()
ctx.fix_pdb.language = "bash"
ctx.fix_pdb.code = 'cat bb_pdb0'
ctx.fix_pdb.bb_pdb0 = ctx.bb_pdb

ctx.pdb = ctx.fix_pdb
ctx.pdb.celltype = "text"
ctx.pdb.share()

ctx.code >> ctx.fix_pdb.code
ctx.code.share()

ctx.save_graph("share-pdb.seamless")
ctx.save_zip("share-pdb.zip")

ctx.code.mount("/tmp/code.bash")
ctx.compute()
