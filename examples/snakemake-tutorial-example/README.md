Snakemake example
=================

Snakefile and data are from the original SnakeMake tutorial, with the following adaptations:

- The original `genome.fa` Snakemake dependency is unclean; `samtools` implicitly depends on `genome.fa.X`, where `X` = `anb`, `ann`, `bwt`, `fai`, `pac`, `sa`.
Therefore, all files have been zipped to `genome.tgz` ; the Snakefile has been adapted accordingly

- Seamless does not yet support Snakemake named inputs that are file lists. The rule `bcftools_call` has been adapted accordingly

- Seamless does not yet support Snakemake run functions, therefore the rule `report` will not work.

- The workflow runs very fast. Therefore, a five-second delay has been introduced for every rule.

How to run the example
======================

You can generate a Seamless graph by binding the Snakefile to the rule `bcftools_call` as follows:
`seamless-run python /home/jovyan/seamless-scripts/snakemake2seamless.py  bcftools_call` 

The script `run-snakegraph.py` binds the contents of `/data` to the graph, and runs the computation. 
NOTE: this script must be run inside a Docker container with samtools, bcftools and bwa installed! This can be done with the command `mamba install -c bioconda -c conda-forge samtools bcftools bwa`.

The Seamless graph can be run interactively using `ipython3 -i run-snakegraph-interactive.py`. This will create a live web page at http://localhost:5813/status/status-visualization.html that constantly shows the progress. 

This will look like this:

![Status visualization animated GIF](run-snakegraph-interactive.gif "Status visualization of the SnakeMake tutorial workflow converted to Seamless")

In summary, the following commands will execute the workflow:

```bash
seamless-bash
python3 ~/seamless-scripts/snakemake2seamless.py bcftools_call
conda config --env --set channel_priority strict
conda install -c bioconda samtools=1.9 bcftools=1.9 bwa=0.7

python3 run-snakegraph.py
# or:
ipython3 -i run-snakegraph-interactive.py  # follow the instructions

```


Results
=======

A file "calls/all.vcf" is generated (and no others). You can then run SnakeMake ("snakemake report") to generate the report.

TODO: let snakemake2seamless report which files must be bound 

TODO: make a generic file binding tool. To make it work seamlessly, create a field {"meta": {"filebind": ("filesystem",)}} that shows to which cell a file must be bound. After that, a generic graph coloring script can do the job => no more run-snakegraph is needed.

TODO: test that shows that the singularity field becomes a Docker transformer.
