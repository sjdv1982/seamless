This example is part of a structural bioinformatics project, related to database searches of protein structure.

It contains two notebooks. For now, the notebooks aren't well-documented, 
and mostly serve as an example how a real-world scientific library, 
written in C, can be wrapped in Seamless.

The scientific library is centered around an algorithm based on 
Binet-Cauchy (BC) kernels, implemented in C by Frederic Guyon 
for various applications (BCLoopSearch, BCSearch, BCScore)

For more details about the algorithm, see the publication:

    Frederic Guyon and Pierre Tuffery
    Fast protein fragment similarity scoring using a Binet-Cauchy Kernel, Bioinformatics, doi:10.1093/bioinformatics/btt618


Web interface
=============

There is currently no web interface. 
In the future, the BC search will be hooked up to a protein viewer, 
 like the one in the share-pdb test:

seamless-serve-graph \
    /home/jovyan/seamless-tests/highlevel/share-pdb.seamless \
    /home/jovyan/seamless-tests/highlevel/share-pdb.zip

=> http://localhost:5813