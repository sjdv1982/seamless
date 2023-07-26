set -u -e -x

rm -rf reuse-vault
python3 reuse-compile1.py
python3 reuse-compile2.py
rm -rf reuse-vault