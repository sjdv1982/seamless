import pexpect, time

ipy = pexpect.spawn("ipython3 --simple-prompt",maxread=1)
def next():    
    ipy.expect([r'In \[\d+\]', pexpect.EOF], timeout=10)    
    print(ipy.before)
    print(ipy.after)

def send(line):
    ipy.sendline(line)
    next()

next()

send("from seamless.workflow import Context")
send("ctx = Context()")
send("ctx.a = 'MYVALUE'")
send("ctx.translate()")
send("import asyncio; await asyncio.sleep(0.5)")
send("print(ctx.a.checksum)")
send("exit()")
