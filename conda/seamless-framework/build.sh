mkdir -p $PREFIX/etc/conda/activate.d
cp bin/activate-seamless-mode.sh $PREFIX/etc/conda/activate.d
$PYTHON setup.py install     # Python command to install the script.
