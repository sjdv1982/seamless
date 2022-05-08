#!/bin/bash
set -u -e -x

comdir=../../docker/commands
mandir=$comdir/doc/man
cd $RECIPE_DIR

cd $mandir
seamless-run-no-shareserver python3 ./build.py
cd $RECIPE_DIR

mkdir -p $PREFIX/bin
mkdir -p $PREFIX/share/man/man1/

for i in $(cat filelist); do
  cp $comdir/$i $PREFIX/bin
  ii=$mandir/build/${i}.1
  if [ -f "$ii" ]; then
    cp $ii $PREFIX/share/man/man1/
  fi
done