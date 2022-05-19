#!/bin/bash
set -u -e -x

comdir=../../docker/commands
docdir=$comdir/doc
cd $RECIPE_DIR

cd $docdir
rm -rf man/build/*.1
seamless-run-no-shareserver python3 man/build.py
cd man
ls build/*.1
cd $RECIPE_DIR

mkdir -p $PREFIX/bin
mkdir -p $PREFIX/share/man/man1/

for i in $(cat filelist); do
  cp $comdir/$i $PREFIX/bin
  ii=$docdir/man/build/${i}.1
  if [ -f "$ii" ]; then
    cp $ii $PREFIX/share/man/man1/
  fi
done