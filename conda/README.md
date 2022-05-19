How to build the seamless-framework Conda package
=================================================

1. Use the same versioning/tag as for Seamless itself. Update the version number in `*/meta.yaml`. Git commit and tag. 

2. From here, launch `conda build seamless-framework -c conda-forge -c rpbs`. Note the output file (.tar.bz2).
If you forget it, run `conda build seamless-framework --output`

3. Upload to anaconda:
```
anaconda login
anaconda upload $filename.tar.bz2
```
