How to build the seamless-framework Conda package
=================================================

1. Use the same versioning/tag as for Seamless itself. Update the version number in `*/meta.yaml`. Git commit and tag. 

2. If you didn't do already, create a conda environment to build and upload conda environments: `conda create -n seamless-build -c conda-forge -c rpbs silk seamless-cli anaconda-client conda-build -y`

3. From here, do `conda activate seamless-build`. Then launch `conda build seamless-framework -c conda-forge -c rpbs`. Note the output file (.tar.bz2).
If you forget it, run `conda build seamless-framework --output`

3. Upload to anaconda:
```
anaconda login
anaconda upload $filename.tar.bz2
```
