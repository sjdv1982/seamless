set -u -e -x

rm -rf reuse-vault
python3 reuse1.py
python3 reuse2.py
python3 reuse3.py
rm -rf reuse-vault