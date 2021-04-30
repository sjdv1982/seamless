# Adapted from SnakeMake source code

from snakemake.workflow import *

# monkey-patch Workflow.execute
def execute(self,
            targets=None,
            dryrun=False,
            touch=False,
            cores=1,
            nodes=1,
            local_cores=1,
            forcetargets=False,
            forceall=False,
            forcerun=None,
            until=[],
            omit_from=[],
            prioritytargets=None,
            quiet=False,
            keepgoing=False,
            printshellcmds=False,
            printreason=False,
            printdag=False,
            cluster=None,
            cluster_sync=None,
            jobname=None,
            immediate_submit=False,
            ignore_ambiguity=False,
            printrulegraph=False,
            printd3dag=False,
            drmaa=None,
            drmaa_log_dir=None,
            kubernetes=None,
            kubernetes_envvars=None,
            container_image=None,
            stats=None,
            force_incomplete=False,
            ignore_incomplete=False,
            list_version_changes=False,
            list_code_changes=False,
            list_input_changes=False,
            list_params_changes=False,
            list_untracked=False,
            list_conda_envs=False,
            summary=False,
            archive=None,
            delete_all_output=False,
            delete_temp_output=False,
            detailed_summary=False,
            latency_wait=3,
            wait_for_files=None,
            nolock=False,
            unlock=False,
            resources=None,
            notemp=False,
            nodeps=False,
            cleanup_metadata=None,
            cleanup_conda=False,
            cleanup_shadow=False,
            subsnakemake=None,
            updated_files=None,
            keep_target_files=False,
            keep_shadow=False,
            keep_remote_local=False,
            allowed_rules=None,
            max_jobs_per_second=None,
            max_status_checks_per_second=None,
            greediness=1.0,
            no_hooks=False,
            force_use_threads=False,
            create_envs_only=False,
            assume_shared_fs=True,
            cluster_status=None,
            report=None,
            export_cwl=False):

    self.check_localrules()

    self.global_resources = dict() if resources is None else resources
    self.global_resources["_cores"] = cores
    self.global_resources["_nodes"] = nodes
    self.immediate_submit = immediate_submit

    def rules(items):
        return map(self._rules.__getitem__, filter(self.is_rule, items))

    if keep_target_files:

        def files(items):
            return filterfalse(self.is_rule, items)
    else:

        def files(items):
            relpath = lambda f: f if os.path.isabs(f) else os.path.relpath(f)
            return map(relpath, filterfalse(self.is_rule, items))

    if not targets:
        targets = [self.first_rule
                    ] if self.first_rule is not None else list()

    if prioritytargets is None:
        prioritytargets = list()
    if forcerun is None:
        forcerun = list()
    if until is None:
        until = list()
    if omit_from is None:
        omit_from = list()

    priorityrules = set(rules(prioritytargets))
    priorityfiles = set(files(prioritytargets))
    forcerules = set(rules(forcerun))
    forcefiles = set(files(forcerun))
    untilrules = set(rules(until))
    untilfiles = set(files(until))
    omitrules = set(rules(omit_from))
    omitfiles = set(files(omit_from))
    targetrules = set(chain(rules(targets),
                            filterfalse(Rule.has_wildcards, priorityrules),
                            filterfalse(Rule.has_wildcards, forcerules),
                            filterfalse(Rule.has_wildcards, untilrules)))
    targetfiles = set(chain(files(targets), priorityfiles, forcefiles, untilfiles))
    if forcetargets:
        forcefiles.update(targetfiles)
        forcerules.update(targetrules)

    rules = self.rules
    if allowed_rules:
        rules = [rule for rule in rules if rule.name in set(allowed_rules)]

    if wait_for_files is not None:
        try:
            snakemake.io.wait_for_files(wait_for_files,
                                        latency_wait=latency_wait)
        except IOError as e:
            logger.error(str(e))
            return False

    dag = DAG(
        self, rules,
        dryrun=dryrun,
        targetfiles=targetfiles,
        targetrules=targetrules,
        # when cleaning up conda, we should enforce all possible jobs
        # since their envs shall not be deleted
        forceall=forceall or cleanup_conda,
        forcefiles=forcefiles,
        forcerules=forcerules,
        priorityfiles=priorityfiles,
        priorityrules=priorityrules,
        untilfiles=untilfiles,
        untilrules=untilrules,
        omitfiles=omitfiles,
        omitrules=omitrules,
        ignore_ambiguity=ignore_ambiguity,
        force_incomplete=force_incomplete,
        ignore_incomplete=ignore_incomplete or printdag or printrulegraph,
        notemp=notemp,
        keep_remote_local=keep_remote_local)
    dag.init()
    return dag

Workflow.execute = execute

# Monkey-patch "run" section of rule
run_functions = {}
def block_content(self, token):
    if self.rulename not in run_functions:
        run_functions[self.rulename] = []
    run_functions[self.rulename].append(token.string)
    return self._block_content(token)

import snakemake.parser
snakemake.parser.Run._block_content = snakemake.parser.Run.block_content
snakemake.parser.Run.block_content = block_content


# Parse arguments
import argparse
parser = argparse.ArgumentParser(
    description="Snakemake2Seamless converter. Snakemake is a Python based language and execution "
    "environment for GNU Make-like workflows")

parser.add_argument("target",
                    nargs="*",
                    default=None,
                    help="Targets to build. May be rules or files.")


parser.add_argument("--snakefile", "-s",
                    metavar="FILE",
                    default="Snakefile",
                    help="The workflow definition in a snakefile.")

parser.add_argument("--seamless",
                    default="snakegraph.seamless",
                    help="Seamless graph file to generate.")

parser.add_argument("--zip",
                    default="snakegraph.zip",
                    help="Seamless zip file to generate.")

import sys
args = parser.parse_args()
assert parse
dag = snakemake.snakemake(
    args.snakefile,
    targets=args.target,
    use_singularity=True
)
if dag == False:
    import sys
    sys.exit()

import seamless
from seamless.highlevel import Context, Transformer, Cell
ctx = Context()
ctx.fs = Context()
fs = ctx.fs
ctx.rules = Context()
ctx.jobs = Context()
ctx.results = Context()
ctx.results2 = Context()

import inspect

class Dummies:
    def __init__(self, d, keys, named):
        self._dict = d
        self._keys = keys
        self._named = named
    def __str__(self):
        d = self._dict
        if self._named:
            return str({k:d[k] for k in self._keys})
        else:
            return " ".join([str(d[k]) for k in self._keys])
    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        if not attr in self._dict:
            raise AttributeError(attr)
        return self._dict[attr]
    def __eq__(self, other):
        return hasattr(other, "_dict") and self._dict == other._dict
    def _tf_params(self):
        default_pin = {
            "transfer_mode": "ref",
            "access_mode": "default",
            "content_type": None,
        }
        return {self._dict[k]: default_pin.copy() for k in self._keys}

def get_dummies(job):
    inkeys = list(job.input.keys())
    inkeys2 = ["_" + k for k in inkeys]
    input_named = True
    if not len(inkeys):
        inkeys = ["input_%d" % n for n in range(1, len(job.input) + 1) ]
        inkeys2 = ["_" + str(n) for n in range(1, len(job.input) + 1) ]
        input_named = False
    if len(inkeys2) == 1:
        inkeys2 = [""]
    input = {k:v for k,v in zip(inkeys, job.input)}
    for k,v in input.items():
        if not isinstance(v, str):
            raise Exception("Inputs must be string: %s , input %s" % (job.name, k))
    indummies = {k1:"inputfile" + k2 for k1,k2 in zip(inkeys, inkeys2)}
    indummies = Dummies(indummies, inkeys, input_named)

    outkeys = list(job.output.keys())
    outkeys2 = ["_"+k for k in outkeys]
    output_named = True
    if not len(outkeys):
        output_named = False
        outkeys = ["output_%d" % n for n in range(1, len(job.output) + 1) ]
        outkeys2 = ["_" + str(n) for n in range(1, len(job.output) + 1) ]
    if len(outkeys2) == 1:
        outkeys2 = [""]
    output = {k:v for k,v in zip(outkeys, job.output)}
    for k,v in output.items():
        if not isinstance(v, str):
            raise Exception("Outputs must be string: %s , output %s" % (job.name, k))
    outdummies = {k1:"outputfile" + k2 for k1,k2 in zip(outkeys, outkeys2)}
    outdummies = Dummies(outdummies, outkeys, output_named)

    wildcard_dummies = {k:"wildcards_" + k for k in job.wildcards_dict}
    wildcard_dummies = Dummies(wildcard_dummies, wildcard_dummies.keys(), True)
    return indummies, outdummies, wildcard_dummies

rules = []
rule_dummies = {}

for job in dag.jobs:
    rule = job.rule
    dummies = get_dummies(job)
    if rule not in rules:
        rules.append(rule)
    else:
        old_dummies = rule_dummies[rule]
        if old_dummies != dummies:
            raise Exception(rule.name, dummies, old_dummies)
    rule_dummies[rule] = dummies

for rule in rules:
    assert not rule.dynamic_output
    assert not rule.is_checkpoint
    if rule.shellcmd is None and rule.name in run_functions:
        raise Exception("rule '%s' has a custom run function, this is not supported" % rule.name)
    if rule.shellcmd is None:
        continue
    indummies, outdummies, wildcard_dummies = rule_dummies[rule]
    shellcmd = rule.shellcmd.format(**{
        "input": indummies, "output": outdummies, "wildcards": wildcard_dummies
    })
    if len(outdummies._keys) == 1:
        shellcmd += ";cat %s > RESULT"  % list(outdummies._dict.values())[0]
    else:
        outputs = " ".join(outdummies._dict.values())
        shellcmd += ";mkdir RESULT; for i in %s; do ii=`dirname $i`; mkdir -p $ii`; mv $i $ii; done" % outputs
    if rule._singularity_img:
        shellcmd = "bash -c '" + shellcmd + "'"

    setattr(ctx.rules, rule.name, shellcmd)
ctx.compute()

def get_jobname(job):
    import re
    def clean(s):
        # From https://stackoverflow.com/a/3303361
        # Remove invalid characters
        s = re.sub('[^0-9a-zA-Z_]', '', s)
        # Remove leading characters until we find a letter or underscore
        s = re.sub('^[^a-zA-Z_]+', '', s)
        return s
    rule = job.rule
    jobname = clean(rule.name)
    for wildcard in rule.wildcard_names:
        wildcard_value = job.wildcards_dict[wildcard]
        if len(rule.wildcard_names) > 1:
            jobname += "_" + clean(wildcard)
        jobname += "_" + clean(wildcard_value)
    return jobname

for job in dag.jobs:
    rule = job.rule
    jobname =  get_jobname(job)
    if not len(job.output):
        print("Skipped job '%s', as it has no outputs" % jobname)
        continue
    print("Creating job:", jobname)

    indummies, outdummies, wildcard_dummies = rule_dummies[rule]
    pins = indummies._tf_params()
    tf = Transformer(pins=pins)
    setattr(ctx.jobs, jobname, tf)

    docker_image = job.singularity_img_url
    if docker_image is not None:
        if not docker_image.startswith("docker://"):
            raise Exception("Docker image '%s' (rule %s) does not start with docker://" % (docker_image, rule.name))
        tf.language = "docker"
        tf.docker_image = docker_image[len("docker://"):]
    else:
        tf.language = "bash"
    tf.code = getattr(ctx.rules, rule.name)

    if not len(job.input.keys()):
        jobinput = job.input
    else:
        jobinput = [job.input[k] for k in job.input.keys()]
    assert len(indummies._keys) == len(jobinput), (list(indummies._keys), jobinput)
    inputs = {k:str(v) for k,v in zip(indummies._keys, jobinput)}
    for k,v in inputs.items():
        if not isinstance(v, str):
            if isinstance(v, list):
                msg = "Rule '%s' (job '%s'): input '%s' is a list instead of a single filename, this is not yet supported"
                raise NotImplementedError(msg % (rule.name, jobname, k))
            else:
                msg = "Rule '%s' (job '%s'): input '%s' should be a string, but it is: '%s'"
                raise TypeError(msg % (rule.name, jobname, k, v))

    if not len(job.output.keys()):
        joboutput = job.output
    else:
        joboutput = [job.output[k] for k in job.output.keys()]
    assert len(outdummies._keys) == len(joboutput), (list(outdummies._keys), joboutput)
    outputs = {k:str(v) for k,v in zip(outdummies._keys, joboutput)}
    for k,v in outputs.items():
        if not isinstance(v, str):
            if isinstance(v, list):
                msg = "Rule '%s' (job '%s'): output '%s' is a list instead of a single filename, this is not yet supported"
                raise NotImplementedError(msg % (rule.name, jobname, k))
            else:
                msg = "Rule '%s' (job '%s'): output '%s' should be a string, but it is: '%s'"
                raise TypeError(msg % (rule.name, jobname, k, v))

    for k,v in inputs.items():
        kk = getattr(indummies,k)
        inp = getattr(fs, v)
        if not isinstance(inp, Cell):
            inp = Cell()
            setattr(fs, v, inp)
        setattr(tf, kk, inp)

    setattr(ctx.results, jobname, tf)
    result = getattr(ctx.results, jobname)
    assert isinstance(result, Cell), type(result)

    if not len(outputs):
        continue

    multi_output = (len(outputs) > 1)

    if multi_output:
        for k,v in outputs.items():
            kk = getattr(outdummies,k)
            setattr(fs, v, getattr(result, kk))
    else:
        (v,) = outputs.values()
        setattr(fs, v, result)

ctx.save_graph(args.seamless)
ctx.save_zip(args.zip)
