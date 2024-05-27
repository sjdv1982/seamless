#!/bin/bash
set -u -e -x

comdir=../../bin
#docdir=$comdir/doc
cd $RECIPE_DIR

#cd $docdir
#rm -rf man/build/*.1
#seamless-run-no-webserver python3 man/build.py
#cd man
#ls build/*.1
#cd $RECIPE_DIR

mkdir -p $PREFIX/etc/conda/activate.d
cp $comdir/activate-seamless-mode.sh $PREFIX/etc/conda/activate.d

mkdir -p $PREFIX/bin

for i in $(cat filelist); do
  cp $comdir/$i $PREFIX/bin
  #ii=$docdir/man/build/${i}.1
  #if [ -f "$ii" ]; then
  #  cp $ii $PREFIX/share/man/man1/
  #fi
done