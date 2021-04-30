function _init {
    export a=`cat a.txt`
}
source bash-preexec.sh
preexec_functions+=(_init)