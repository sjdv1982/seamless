HHSUITE1 = "hhblits-local.sh" #or w.Invariant("hhblits-local.sh"); changing this shouldn't influence the result
HHSUITE2 = "hhsearch-local.sh"
BANKDIR1 = w.Variable("/home/sjoerd/uniprot20") #changing this DOES change the result
BANKNAME1 = w.Variable("uniprot20_2016_02")
BANKDIR2 = w.Variable("/home/sjoerd/pdb70")
BANKNAME2 = w.Variable("pdb70")
BANKNAME2A = BANKNAME2
PSIPRED = "/home/sjoerd/software/psipred" #again, this shouldn't influence the result
if HHSUITE2.startswith("hhsearch"):
    BANKNAME2A=BANKNAME2+"_hhm_db"
MAX_SEQID=50
CORES=8

import workflow as w

date = w.time.tomorrow("timestamp.txt")  #w.Time, subclass of w.File

#1. Download CASP11 targets into f_targetlist_cgi
f_targetlist_cgi = w.File("targetlist.cgi")
p_targetlist = w.programs.webcache() #(subclass of) w.CacheProgram, subclass of w.Program
p_targetlist.input = w.Link("http://www.predictioncenter.org/casp11/targetlist.cgi") #subclass of w.File, never monitored explicitly
p_targetlist.expire = date
p_targetlist.output = f_targetlist_cgi #sets f_targetlist.process = p_targetlist; exception if .process already defined

#2. Parse CASP11 target list into f_targetlist, f_fasta, f_pdbs, f_pdb_alignments
#TODO: make version for CASP12 that does not create f_pdbs, f_pdb_alignments
f_targetlist = w.File("targets.list")
p_parse_casp11 = w.Python() #subclass of w.Script, subclass of w.Program, subclass of w.Process
p_parse_casp11.script = w.File("parse_casp11.py") #must be w.File so we can cache it!
p_parse_casp11.input = f_targetlist_cgi
p_parse_casp11.program = "python" #optional
p_parse_casp11.cmdargs = "i>o"
p_parse_casp11.output = f_targetlist

targets = f_targetlist.readlines() #w.DataList = dynamic data list
"""
or:
targets = w.operator.readlines(targetlist)
or:
targets = targetlist.read().splitlines().strip().filter(filt)
 "readlines": File => DataList
 "read": File => Data
 "splitlines": Data => DataList
 "strip": Data => Data or DataList => DataList
"""

#f_fasta: list of query sequence files
f_fasta = targets.filename("fasta/%s.fas") #w.FileDList = dynamic file list
#f_pdbs: list of golden standard PDBs
f_pdbs = targets.filename("pdbs/%s.pdb")
#f_pdb_alignments: list of golden standard PDB alignments
f_pdb_alignments = targets.filename("pdb_alignments/%s")
p_parse_casp11.implicit_output = [f_pdbs, f_pdb_alignments]

#3: Filter the target list
"""
with this, we can manually edit the f_targetlist and comment out targets
BUT: realize that f_targetlist will be overwritten every day!
     and also, whenever we change parse_casp11.py!
"""
filt = lambda l: len(l) and l.find("#") == -1
targets = targets.filter(filt)
#reconstruct f_fasta
f_fasta = targets.filename("fasta/%s.fas")

#3a: define HHSUITE directory
#fd_hhsuite: directories with alignments and templates for each target
fd_hhsuite = targets.dirname("hhsuite/%s") #w.DirectoryDList
fd_hhsuite.monitor = False
#monitor is False, because we aren't interested in all files, only specific ones

#4: run HHSUITE1 (hhblits) to build alignments
p_hhsuite1 = w.Bash()
p_hhsuite1.script = w.File(HHSUITE1)
assert HHSUITE1.find("hhblits") > -1, HHSUITE1
args = "-d {BANKDIR1}/{BANKNAME1} -n 4 -cpu {CORES} -addss -psipred {PSIPRED}/bin/ p_hhsuite1.argument -psipred_data {PSIPRED}/data/"
p_hhsuite1.arguments = args.format(**dict(globals()))
p_hhsuite1.dependencies = [BANKDIR1, BANKNAME1] #w.Variable
p_hhsuite1.cmdargs = "ioa"

pp_hhsuite1 = w.Pool(p_hhsuite1, np=1) #creates a w.Pool of programs
#we want to run only 1 at a time because HHsuite already uses 8 CPUs
#w.Pool takes a File(D)List instead of File(D) as an input
pp_hhsuite1.input = f_fasta
#w.Pool takes a File(D)List instead of File(D) as an output
# in our case, it is a DirectoryDList
pp_hhsuite1.output = fd_hhsuite

f_hhsuite1_result = w.List(type=w.FileDList)() #better than [], because workflow can now infer that f is called "f_hhsuite1_result[<it>]"
for it in range(4):
    f = fd_hhsuite.filename("%%s/hhblits-it_%d.a3m" % (it+1), if_exist=True) #w.FileDList
    #only generate those files that exist
    f.monitor = False #we may not care about all iterations
    f_hhsuite1_result.append(f)

#5: run HHSUITE2 (hhsearch) to identify PDB templates
#for now, run it on all iterations (last one would be sufficient)
f_hhsuite2_result = w.List(type=w.DirectoryDList)() #better than [], because workflow can now infer that f is called "f_hhsuite1_result[<it>]"
for it in range(4):
    p_hhsuite2 = w.Bash()
    p_hhsuite2.script = w.File(HHSUITE2)
    args = "-d {BANKDIR2}/{BANKNAME2A} -cpu 8"
    if HHSUITE2.find("hhsearch") > -1:
        args += " -n 1"
    p_hhsuite2.arguments = args.format(**dict(globals()))
    p_hhsuite1.dependencies = [BANKDIR2, BANKNAME2)]

    pp_hhsuite2 = w.Pool(p_hhsuite2, np=1) #creates a w.Pool of programs
    #we want to run only 1 at a time because HHsuite already uses 8 CPUs
    pp_hhsuite2.input = f_hhsuite1_result[it]
    f = fd_hhsuite.dirname("%%s/pdb-it_%d" % (it+1)) #w.DirectoryDList
    f.monitor = False #we don't care about all files (HHsearch / HHblits wrappers create quite a few extra)
    fd_hhsuite2_result.append(f)
    pp_hhsuite2.output = f

#6: Select the result file we are going to use (delayed), selecting the last iteration
def selectfunc():
    if HHSUITE2.find("hhsearch") > -1:
        outp = "hhsearch"
    else:
        outp = "hhblits"
    #len(targets) is only possible once targets has become real
    for n in range(len(targets)):
        target = targets[n]
        targetdir = fd_hhsuite[n] #w.DirectoryD
        t = targetdir.value
        found = False
        for it in reversed(list(range(4))):
            #iterator over fd_hhsuite2_result is only possible once it has become real
            for rr in fd_hhsuite2_result[it]: #w.DirectoryD
                if rr.value.startswith(t):
                    f_hhr = rr.filename("%%s/pdb_it%d/%s.hhr" % (it+1, outp)) #w.FileD
                    assert f_hhr.exists()
                    f_pairwise = rr.filename("%%s/pdb_it%d/%s_pairwise.fas" % (it+1,outp)) #w.FileD
                    assert f_pairwise.exists()
                    f_hhsuite_hhr.append(f_hhr.copy("%%s/pdb/%s.hhr" % outp)
                    f_hhsuite_pairwise.append(f_pairwise.copy("%%s/pdb/%s_pairwise.fas" % outp)
                    found = True
                    break
            if found: break

f_hhsuite_hhr = w.FileDList()
f_hhsuite_pairwise = w.FileDList()
#delayed construction of f_hhsuite_hhr and f_hhsuite_fas
# we can't construct them yet since they depend on fd_hhsuite2_result[:4] being real (i.e.), not dynamic
w.delay(output=[f_hhsuite_hhr, f_hhsuite_pairwise], input= fd_hhsuite2_result, func=selectfunc)

#7: Realign the pdbs (for now, dummy method)
fd_pdb_alignments = targets.dirname("hhsuite/%s/pdb-alignments") #w.DirectoryDList()
fd_pdb_alignments.monitor = False
f_template_dirlists = targets.filename("hhsuite/%s/pdb-alignments/list.txt", defined=False)
f_templates_stat = targets.filename("hhsuite/%s/pdb-alignments/templates.stat", defined=False)
p_realign = w.Python()
p_realign.script = w.File("realign-dummy.py")
p_realign.cmdargs = "ia>o"
pp_realign = w.Pool(p.realign, np=CORES)
pp_realign.input = [f_hhsuite_hhr, f_hhsuite_pairwise]
pp_realign.arguments = fd_pdb_alignments
pp_realign.output = f_template_dirlists
pp_realign.implicit_output = [fd_pdb_alignments, f_templates_stat]

f_template_dirs = f_template_dirlists.readlines()
#w.DirectoryDListDList: a dynamic list of dynamic lists of directories
f_template_dirs_fas = f_template_dirs.filename("%s/template.fas", defined=True) #w.FileDListDList
#defined=True (default) means that f_template_dirs_fas_filtered was created when f_template_dirs was created
f_template_dirs_fas_filtered = f_template_dirs.filename("%s/template-filtered.fas", defined=False) #w.FileDListDList
#f_template_dirs_fas_filtered was NOT created when f_template_dirs was created!

#8: filter alignments
p_pdb_alignment_filter = w.Python()
p_pdb_alignment_filter.script = w.File("pdb-alignment-filter.py")
p_pdb_alignment_filter.arguments = [BANKDIR2, BANKNAME2]
p_pdb_alignment_filter.cmdargs = "ia>o"
pp_pdb_alignment_filter = w.Pool(w.Pool(p_pdb_alignment_filter, np=CORES)) #pool of pools, takes a FileDListDList as argument
pp_pdb_alignment_filter.input = f_template_dirs_fas
pp_pdb_alignment_filter.output = f_template_dirs_fas_filtered

#9: prepare MODELLER
fd_models = targets.dirname("models/%s") #w.DirectoryDList
fd_models.monitor = False #MODELLER will later write a lot more files
p_prepare_modeller = w.Python()
p_prepare_modeller.script = w.File("prepare-modeller.py")
p_prepare_modeller.cmdargs = "ioa"
pp_prepare_modeller = w.Pool(p_prepare_modeller, np=CORES)
pp.input = [f_fasta, fd_pdb_alignments]
pp.output = fd_models
pp.dependencies = [f_template_dirs_fas_filtered, f_templates_stat]
pp.arguments = [MAX_SEQID, BANKDIR2, BANKNAME2]

#9a: identify the templatesets
fd_templatesets = fd_models.globdir([
"%s/templateset-?",
"%s/templateset-??",
"%s/templateset-???",
"%s/templateset-????"
], defined=True) #w.DirectoryDListDList
fd_templatesets_list = fd_templatesets.write("%s/templatesets.list")#w.DirectoryDList
#fd_templatesets was created when fd_models was created
fd_templatesets.monitor = False #MODELLER will write a lot more files

fd_templatesets_alignments = fd_templatesets.filename("%s/alignment.pir", exist=True) #w.FileDListDList
#verify that the files exist once fd_templatesets was created
#we will monitor fd_templatesets_alignments, so we know when to re-run prepare-modeller.py
# every process needs to have at least one monitored input or dependency!
fd_templatesets_alignments.monitor = True #not strictly needed, because default


#10: run MODELLER
#MODELLER will modify the templatesets directories, adding additional files there
#This is hard to describe in terms of dependencies:
# we can think of it as templatesets => run-modeller.py => templatesets_post
# so we create a new dirname target fd_templatesets_post that has the exact same directory name as fd_templatesets
#It is not defined by
fd_templatesets_post = fd_templatesets.dirname("%s", defined=False, monitored=False)
fd_templatesets_model = fd_templatesets_post.filename("%s/model-9999-0001.pdb", exist=False)

p_run_modeller = w.Python()
p_run_modeller.script = "run-modeller.py"
p_run_modeller.cmdargs = "i>&o"
pp_run_modeller = w.Pool(w.Pool(p_run_modeller, np=CORES)) #pool of pools, takes a FileDListDList as argument
pp_run_modeller.input = fd_templatesets
pp_run_modeller.log_output = fd_templatesets.filename("%s/modeller.log", monitored=False)
pp_run_modeller.dependencies = fd_templatesets_alignments
pp_run_modeller.implicit_output = [fd_templatesets_post, fd_templatesets_model]

#11: evaluate results (only the non-loop-refined ones)
f_evaluate = fd_models.filename("%s/evaluate.txt")
p_evaluate_all = w.Bash()
p_evaluate_all.script = "evaluate-all.sh"
pp_evaluate_all = w.Pool(p_evaluate_all, np=CORES)
pp_evaluate_all.dependencies = fd_templatesets_model
pp_evaluate_all.side_output = f_evaluate

#12: select templates for MODELLER loop modelling
p_select_loopmod_templates = w.Python()
p_select_loopmod_templates.script = "select-loopmod-templates.py"
p_select_loopmod_templates.dependencies = f_evaluate
p_select_loopmod_templates.cmdargs = ""
f_loopmod_templates = w.File("loopmod-templates.list")
p_select_loopmod_templates.implicit_output = f_loopmod_templates
fd_templatesets_loop = w.DirectoryDList(f_loopmod_templates.readlines(), exist=True, monitored=False)

#13: run MODELLER loop
fd_templatesets_loop_models = fd_templatesets_loop.glob("%s/model-*.pdb", exist=False)

p_run_modeller_loop = w.Python()
p_run_modeller_loop.script = "run-modeller-loop.py"
p_run_modeller_loop.cmdargs = "i>&o"
pp_run_modeller_loop = w.Pool(p_run_modeller, np=CORES))
pp_run_modeller_loop.input = fd_templatesets_loop
pp_run_modeller_loop.log_output = fd_templatesets_loop.filename("%s/modeller-loop.log", monitored=False)
pp_run_modeller_loop.implicit_output = fd_templatesets_loop_models

#14: build BCsearch benchmark

"""
w.Program
.output (or .implicit_output + .log_output) is always defined
  .output is a monitored file target (File or FileD) that is explicitly specified to the program (an output group token must have been specified).
  .implicit_output are monitored file targets (File or FileD, or a Python list of those) that are not explicitly specified to the program, but nevertheless depend on it.
  .log_output is a non-monitored file target (File, FileD or string) that are specified to the program (typically, some kind of log file). Requires .implicit_output to be defined.
For every item in .output or .implicit_output it holds that it must be either monitored, or must be the basis of an operator expression that is monitored.

.parameterlist is a list where each item is a string $name or a tuple ($name, $parname)
If the item is a string, $parname = $name
$name may not be "program", "input", "output", "arguments", "parameterlist" or a class attribute

cmdargs in w.Program
"cmdargs" is a string consisting of any number of tokens. Each token belongs to one group: input, argument, parameter or output.
The tokens can be in any order (except that >o must be last)
Examples:
  "i>o" => program input > output
    .program = "cat"
    .input = w.File("~/.bashrc")
    .output = w.File("~/.bashrc-BACKUP")
    => cat ~/.bashrc > ~/.bashrc-BACKUP
  "-aoi" => program arguments output input
    .program = "tar"
    .input = w.Directory("/home/user")
    .output = w.File("/tmp/backup.tgz")
    .arguments = "-czf"
    => tar -czf /tmp/backup.tgz /home/user
  "--poi" => program parameters output input
    .program = "tar"
    .input = w.Directory("/home/user")
    .output = w.File("/tmp/backup.tgz")
    .output_token = "--file"
    .parameterlist = ["create", "gzip", "verbose"]
    .create = True
    .gzip = True
    .verbose = False
    => tar --create --gzip --file /tmp/backup.tgz /home/user
       #NOT_REQUIRED --verbose since it was specified as False; NOT_REQUIRED specification gives an error
  "-ai" => program parameters input
    .program = "tar"
    .output = w.Directory(os.getcwd())
    .input = "/home/user"
    .arguments = "-xvzf"
    => tar -xvzf /tmp/backup.tgz

Tokens per group

Input group:
i: prints .input
I: prints "-i " + .input. "i" may not be present in .parameterlist. '-i' can be overruled with .input_token

Argument group:
a: prints " ".join([a for a in .arguments]) if .arguments is not a string already

Parameter group:
--p:
  requires non-empty .parameterlist;  All parameters in .parameterlist are rendered as:
   '--$parname' if isinstance(parametervalue, bool) and parameter == True
   '--parname $parametervalue' otherwise
-p: same as above, but -$parname is used instead of --$parname
p: same as above, but NOT_REQUIRED - is added, meaning that $parname must start with at least one - (validated)

Output group:
.output can be understood as .log_output, but only one can be defined
o: prints .output
O: prints "-o " + .output. "o" may not be present in .parameterlist. '-o' can be overruled with .output_token.
>o: prints "> " + .output . Must be the last token
>&o: prints ">& " + .output . Must be the last token

For w.Script, "program" means "<program> <script>", i.e. "python script.py"
"""
