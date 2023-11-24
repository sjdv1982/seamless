rm -rf scratch-fingertip
mkdir scratch-fingertip
cd scratch-fingertip
seamless --scratch -c 'awk '\''BEGIN{print 3}'\'' > three.txt'
echo
cat three.txt
echo
cat three.txt.CHECKSUM
echo
seamless-download three.txt.CHECKSUM
echo
cat three.txt
echo
echo Fingertip...
seamless-fingertip three.txt.CHECKSUM > three.txt
cat three.txt
echo /Fingertip
rm -f three.txt

echo
echo

seamless --scratch -c 'cat three.txt three.txt | awk '\''{x+=$1} END{print x}'\'' > six.txt'
echo
cat six.txt
echo
cat six.txt.CHECKSUM
echo
seamless-download six.txt.CHECKSUM
echo
cat six.txt
echo
echo Fingertip...
seamless-fingertip six.txt.CHECKSUM > six.txt
cat six.txt
echo /Fingertip
rm -f six.txt

cd ..
rm -rf scratch-fingertip
