#!/bin/bash
set -e

if [ -z "$SEAMLESS_SCRIPT_DIR" ]; then
  export SEAMLESS_SCRIPT_DIR=~/seamless-scripts
fi

set -u -e

tempfile=$(mktemp)
tf_checksum=$(python3 transformation-checksum.py 2> /dev/null)
echo ''
echo '*********************************************************************************************'
echo "Transformation checksum: " $tf_checksum
echo '*********************************************************************************************'
echo ''
python3 -u $SEAMLESS_SCRIPT_DIR/run-transformation.py $tf_checksum --direct-print| tee $tempfile
result_checksum=$(tail -1 $tempfile)
echo ''
echo '*********************************************************************************************'
echo "Result checksum:" $result_checksum
echo '*********************************************************************************************'
echo ''
echo "Re-run 1..."
python3 -u $SEAMLESS_SCRIPT_DIR/run-transformation.py $tf_checksum --direct-print | tee $tempfile
result_checksum=$(tail -1 $tempfile)
echo "Result checksum:" $result_checksum
echo "Delete transformer result"
python3 $SEAMLESS_SCRIPT_DIR/delete-transformation-result.py $tf_checksum
echo "Re-run 2..."
python3 -u $SEAMLESS_SCRIPT_DIR/run-transformation.py $tf_checksum --direct-print | tee $tempfile
result_checksum=$(tail -1 $tempfile)
echo "Result checksum:" $result_checksum
echo "Re-run 3..."
python3 -u $SEAMLESS_SCRIPT_DIR/run-transformation.py $tf_checksum --direct-print | tee $tempfile
result_checksum=$(tail -1 $tempfile)
echo "Result checksum:" $result_checksum
value=$(python3 $SEAMLESS_SCRIPT_DIR/resolve.py $result_checksum plain)
echo ''
echo '*********************************************************************************************'
echo "Value " $value
echo '*********************************************************************************************'
python3 $SEAMLESS_SCRIPT_DIR/delete-transformation-result.py $tf_checksum
echo ''
rm -rf $tempfile
