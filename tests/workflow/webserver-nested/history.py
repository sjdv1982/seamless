seamless.config.unblock_local()
ctx.load_vault("vault/")  # bug/gotcha in new-project.py

ctx.master_seed = Cell("int").set(0)
ctx.master_seed.share(readonly=False)

ctx.njobs = Cell("int").set(10)
ctx.njobs.share(readonly=False)


def calc_seeds(njobs, master_seed):
    import numpy as np

    np.random.seed(master_seed)
    seeds = np.random.randint(0, 999999, njobs)
    direct_job_seeds = seeds[0::2]
    cmd_job_seeds = seeds[1::2]
    return direct_job_seeds, cmd_job_seeds


ctx.calc_seeds = calc_seeds
ctx.calc_seeds.master_seed = ctx.master_seed
ctx.calc_seeds.njobs = ctx.njobs
ctx.seeds = ctx.calc_seeds.result
ctx.direct_job_seeds = ctx.seeds[0]
ctx.cmd_job_seeds = ctx.seeds[1]

ctx.ndots_oom = Cell("int").set(8)  # or 9
ctx.ndots_oom.share(readonly=False)
ctx.calc_ndots = lambda oom: 10**oom
ctx.calc_ndots.oom = ctx.ndots_oom
ctx.ndots = ctx.calc_ndots.result
ctx.ndots.celltype = "int"

ctx.direct_job = Transformer()
ctx.direct_job.code.mount("direct-job.py")
ctx.direct_job.seeds = ctx.direct_job_seeds
ctx.direct_job.seeds.celltype = "binary"
ctx.direct_job.ndots = ctx.ndots

ctx.calc_pi = Cell("text").mount("calc_pi.py")
ctx.cmd_job = Transformer()
ctx.cmd_job.language = "bash"

ctx.cmd_job.code.mount("cmd-job.sh")
ctx.cmd_job["seeds.npy"] = ctx.cmd_job_seeds
ctx.cmd_job["seeds.npy"].celltype = "binary"
ctx.cmd_job["calc_pi.py"] = ctx.calc_pi
ctx.cmd_job.ndots = ctx.ndots

ctx.pi_direct_job = ctx.direct_job.result
ctx.pi_direct_job.celltype = "float"
ctx.pi_direct_job.share()

ctx.pi_cmd_job = ctx.cmd_job.result
ctx.pi_cmd_job.celltype = "float"
ctx.pi_cmd_job.share()

ctx.translate()
