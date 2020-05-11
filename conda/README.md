How to build the Conda packages
===============================

1. Check yourself if the package needs to be rebuilt. Conda gives a different .tar.bz2 checksum for every build, very annoying.
The Git tag system is e.g "v.0.1.1-seamless-cli". Use `git tag -l` to find the recent one.
Then do `git log $tag docker/commands` to see what has changed.

2. Update the version number in `*/meta.yaml`. Git commit and tag.

3. From here, launch `conda build seamless-cli` and/or `conda build seamless-cli-devel` . Note the output file (.tar.bz2).

4. Upload to anaconda:
```
anaconda login
anaconda upload $filename.tar.bz2
```