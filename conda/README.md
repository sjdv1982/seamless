How to build the CLI Conda packages
===================================

1. Check yourself if the package needs to be rebuilt. Conda gives a different .tar.bz2 checksum for every build, very annoying.
The Git tag system is e.g "v.0.1.1-seamless-cli". Use `git tag -l` to find the recent one.
UPDATE: now use same versioning/tag as for Seamless itself
Then do `git diff $tag docker/commands` to see what has changed.

2. Update the version number in `*/meta.yaml`. Git commit and tag.

3. From here, launch `conda build seamless-cli`. Note the output file (.tar.bz2).
If you forget it, run `conda build seamless-cli --output`

4. Upload to anaconda:
```
anaconda login
anaconda upload $filename.tar.bz2
```

How to build the seamless-framework Conda package
=================================================
conda build seamless-framework -c conda-forge -c rpbs