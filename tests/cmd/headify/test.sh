OLD_PATH=$PATH

function run() {
    cmd=$1
    workfiles=$2
    shift 2
    rm -rf $workfiles
    cp -r files/ $workfiles
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
run "seamless -w $(pwd) headify" workfiles >& tee test-run4.out
echo


export PATH=$(pwd)/inferior-interface:$OLD_PATH
time (
echo 'Run 5 (seamless, inferior interface, 3 sec sleep)...'
run "seamless -w $(pwd) headify" workfiles --sleep 3 >& test-run5.out
)
echo

time (
echo 'Run 5a (seamless, inferior interface, 3 sec sleep, repeat)...'
run "seamless -w $(pwd) headify" workfiles --sleep 3 >& test-run5a.out
)
echo

time (
echo 'Run 6 (seamless, inferior interface, 3 sec sleep, rename)...'
run "seamless -w $(pwd) headify" new-workfiles --sleep 3 >& test-run6.out
)
echo

echo 'Run 7 (seamless, superior interface)...'
export PATH=$(pwd)/superior-interface:$OLD_PATH
run "seamless -w $(pwd) headify" workfiles >& tee test-run7.out
exit
