set -u -e
function report() {
    cat /tmp/collatz
}
trap report ERR
for i in `seq 100`; do 
    python3 -u collatz.py  > /tmp/collatz 2>&1
    echo $i
done