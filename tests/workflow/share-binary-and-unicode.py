from seamless.workflow import Context, Cell

ctx = Context()
ctx.cow = Cell("bytes").set(open("cow.jpg", "rb").read())
ctx.cow.share("cow.jpg", readonly=False)
ctx.cow.mimetype = "jpg"
ctx.unicode = Cell("text")
ctx.unicode.set("Touché")
ctx.unicode.share("unicode.txt", readonly=False)
ctx.compute()
