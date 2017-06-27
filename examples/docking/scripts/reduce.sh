x=`mktemp`
python $ATTRACTTOOLS/reduce.py $1 $x > /dev/null
cat $x
rm -f $x
