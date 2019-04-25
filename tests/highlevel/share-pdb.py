from seamless.highlevel import Context, Transformer

ctx = Context()

ctx.pdb0 = open("1crn.pdb").read()
ctx.pdb0.celltype = "text"
ctx.pdb0.share()

ctx.filter_pdb = Transformer()
ctx.filter_pdb.language = "bash"
ctx.filter_pdb.code = "grep ATOM pdb0 | head -50"
ctx.filter_pdb.pdb0 = ctx.pdb0

ctx.pdb = ctx.filter_pdb
ctx.pdb.celltype = "text"
ctx.pdb.share()

ctx.code >> ctx.filter_pdb.code
ctx.code.share()

ctx.code.mount("/tmp/code.bash")
ctx.equilibrate()
