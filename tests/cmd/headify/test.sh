OLD_PATH=$PATH

function run() {
    cmd=$1
    workfiles=$2
    shift 2
    rm -rf $workfiles
    cp -r files/ $workfiles
    # The following three commented lines work too...
    #cd $workfiles
    #$cmd text.txt -n 3 $*
    #cd ..
    $cmd $workfiles/text.txt -n 3 $*
    ls $workfiles/
    echo
    cat $workfiles/text-head.txt
    echo

    $cmd $workfiles/filelist.txt -n 3 --batch $*
    cd $workfiles
    ls
    echo
    cat numbers-head.dat
    echo
    cat table-head.csv
    echo    
    cd ..
    rm -rf $workfiles
}

function run999() {
    rm -rf workfiles
    cp -r files/ workfiles
    seamless -g2 -c '
touch workfiles/text.txt inferior-interface/headify inferior-interface/headify_lib.py
cp workfiles/text.txt TEST.txt
inferior-interface/headify TEST.txt -n 4
inferior-interface/headify workfiles/text.txt -n 3
'
    mv TEST* workfiles/ 
    ls workfiles/
    echo
    cat workfiles/TEST-head.txt
    echo
    cat workfiles/text-head.txt
    rm -rf workfiles
}

function run1000() {
    rm -rf workfiles
    cp -r files/ workfiles
    seamless -g2 -c '
touch workfiles/text.txt canonical-interface/headify canonical-interface/headify_lib.py
cp workfiles/text.txt TEST.txt
canonical-interface/headify TEST.txt -n 4
canonical-interface/headify workfiles/text.txt -n 3
'
    mv TEST* workfiles/ 
    ls workfiles/
    echo
    cat workfiles/TEST-head.txt
    echo
    cat workfiles/text-head.txt
    rm -rf workfiles
}

export PATH=$(pwd)/bin:$OLD_PATH

echo 'Run 1 (no seamless)...'
run headify workfiles >& test-run1.out
echo

echo 'Run 2 (seamless, no interface)...'
run "seamless -w $(pwd) headify" workfiles >& test-run2.out
echo

echo 'Run 3 (seamless, partial interface)...'
export PATH=$(pwd)/partial-interface:$OLD_PATH
run "seamless -w $(pwd) headify" workfiles >& test-run3.out
echo

echo 'Run 4 (seamless, inferior interface)...'
export PATH=$(pwd)/inferior-interface:$OLD_PATH
run "seamless -w $(pwd) headify" workfiles >& test-run4.out
echo

export PATH=$(pwd)/inferior-interface:$OLD_PATH
time (
echo 'Run 5 (seamless, inferior interface, 2x5 sec sleep)...'
run "seamless -w $(pwd) headify" workfiles --sleep 5 >& test-run5.out
)
echo

time (
echo 'Run 5a (seamless, inferior interface, 2x5 sec sleep, repeat)...'
run "seamless -w $(pwd) headify" workfiles --sleep 5 >& test-run5a.out
)
echo

time (
echo 'Run 6 (seamless, inferior interface, 2x5 sec sleep, rename)...'
run "seamless -w $(pwd) headify" new-workfiles --sleep 5 >& test-run6.out
)
echo

echo 'Run 999 (seamless, inferior interface, multi-command)...'
run999  >& test-run999.out
echo

echo 'Run 7 (seamless, canonical interface)...'
export PATH=$(pwd)/canonical-interface:$OLD_PATH
run "seamless -w $(pwd) headify" workfiles >& test-run7.out
echo

echo 'Run 1000 (seamless, canonical interface, multi-command)...'
echo 'FAILS because canonical interface is for single-command only'
run1000  >& test-run1000.out
echo

time (
echo 'Run 8 (seamless, canonical interface, 2x5 sec sleep)...'
export PATH=$(pwd)/canonical-interface:$OLD_PATH
run "seamless headify" workfiles --sleep 5 >& test-run8.out
)
echo

time (
echo 'Run 8a (seamless, canonical interface, 2x5 sec sleep, repeat)...'
export PATH=$(pwd)/canonical-interface:$OLD_PATH
run "seamless headify" workfiles --sleep 5 >& test-run8a.out
)
echo

time (
echo 'Run 9 (seamless, inferior interface, 2x5 sec sleep, rename)...'
echo 'Time should be around 5+2 secs instead of 10+2'
echo 'The first command of run() is now canonical and federates upon rename'
export PATH=$(pwd)/canonical-interface:$OLD_PATH
run "seamless headify" new-workfiles --sleep 5 >& test-run9.out
)
echo

echo 'headify workflow version: should federate and return immediately'
python3 headify-workflow.py files/text.txt -n 3 --sleep 5