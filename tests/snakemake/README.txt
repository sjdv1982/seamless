Adapted from the original SnakeMake tutorial

- The original genome.fa dependency is unclean; samtools implicitly depends on genome.fa.X, where X = anb, ann, bwt, fai, pac, sa.
Therefore, all files have been zipped to genome.tgz; the Snakefile has been adapted accordingly

- Seamless does not yet support named inputs that are file lists. The rule "rule bcftools_call" has been adapted accordingly

- Seamless does not yet support run functions, therefore the rule "report" will not work.

You can generate a Seamless graph by binding the Snakefile to the rule "bcftools_call" as follows:
python3 ../../scripts/snakemake2seamless.py  bcftools_call  --seamless snakegraph.seamless --zip snakegraph.zip

The script run-snakegraph.py binds the contents of "data" to the graph, and equilibrates it.

A file "calls/all.vcf" is generated (and no others). You can then run SnakeMake to generate the report.

TODO: let snakemake2seamless report which files must be bound 
TODO: make a generic file binding tool. To make it work seamlessly, create a field {"meta": {"filebind": ("filesystem",)}} that shows to which cell a file must be bound. After that, a generic graph coloring script can do the job => no more run-snakegraph is needed.
TODO: test that shows that the singularity field becomes a docker transformer.
