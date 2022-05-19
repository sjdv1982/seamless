"""Converts .md files to Unix man files using pandoc and Seamless

TODO: Store as a single Seamless graph, as soon as Seamless has map-reduce
"""

docdir = ".."
buffer_cache = "seamless-buffer-cache.zip"
result_cache = "seamless-result-cache.dat"

import glob, os
from seamless.highlevel import Context, Transformer, Cell
currdir=os.path.dirname(os.path.realpath(__file__))
print("MAN DOC CURRDIR", currdir)
os.chdir(currdir)

docfiles0 = glob.glob("{}/*.md".format(docdir))
docfiles = [os.path.splitext(
              os.path.split(f)[1]
            )[0] for f in docfiles0]
print("DOCFILES", docfiles)

# TODO: make a real API for this
from seamless.core.cache.transformation_cache import transformation_cache
if os.path.exists(result_cache):
    with open(result_cache) as f:
        for line in f:
            tf_checksum, result_checksum = line.split()
            tf_checksum = bytes.fromhex(tf_checksum)
            result_checksum = bytes.fromhex(result_checksum)
            transformation_cache.transformation_results[tf_checksum] = \
              result_checksum, False

# /TODO

ctx = Context()

if os.path.exists(buffer_cache):
    ctx.add_zip(buffer_cache)

ctx.pandoc = """
ln -s inputfile input.md
pandoc --standalone --to man input.md -o RESULT
"""
for f in docfiles:
    setattr(ctx, f, Context())
    sctx = getattr(ctx, f)
    md = "{}/{}.md".format(docdir, f)
    sctx.md = Cell("text").set(open(md).read())
    tf = sctx.tf = Transformer()
    tf.language = "bash"
    tf.scriptname = f
    tf.inputfile = sctx.md
    tf.code = ctx.pandoc
    sctx.result = tf
    sctx.result.celltype = "text"
    sctx.result.mount("build/{}.1".format(f), "w")

ctx.compute()
print("Exception:")
print(ctx["seamless-bash"].tf.exception)
print(ctx["seamless-bash"].result.value)
print()

ctx.save_zip(buffer_cache)

# TODO: make a real API for this
from seamless.core.cache.transformation_cache import transformation_cache

with open(result_cache, "w") as result_cache:
    for tf_checksum, (result_checksum, prelim) in sorted(
    transformation_cache.transformation_results.items()
    ):
        if not prelim:
            print(
                tf_checksum.hex(),
                result_checksum.hex(),
                file=result_cache
            )
# / TODO