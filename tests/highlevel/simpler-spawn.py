# DOES NOT WORK as of Nov 2018

def triple_it(a):
    return 3 * a

def triple_it_b(a, b):
    return 3 * a + b

if __name__ == "__main__":

    # force the use of processes
    import os
    os.environ["SEAMLESS_USE_PROCESSES"] = "true"

    #set multiprocessing to "spawn", as it would be on Windows
    import multiprocessing
    multiprocessing.set_start_method("spawn")

    from seamless.highlevel import Context

    ctx = Context()
    #ctx.mount("/tmp/mount-test")

    ctx.a = 12

    ctx.transform = triple_it
    ctx.transform.a = ctx.a
    ctx.myresult = ctx.transform
    ctx.equilibrate()
    print(ctx.myresult.value)

    ctx.tfcode >> ctx.transform.code
    print(ctx.tfcode._get_hcell())
    print(ctx.tfcode.value)
    ctx.transform.b = 100
    ctx.tfcode = triple_it_b
    ctx.equilibrate()
    print(ctx.myresult.value)
    print("START")
    ctx.a = 13
    ctx.equilibrate()
    print(ctx.myresult.value)
