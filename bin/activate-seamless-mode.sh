function _seamless_complete() {
    READLINE_LINE=$(_seamlessify $READLINE_LINE @@@ $SEAMLESS_MODE_OPTS)
}

function seamless-mode() {
    if [ -z "$_SEAMLESS_MODE_OLD_PS1" ]; then
        _SEAMLESS_MODE_OLD_PS1=$PS1
        PS1='\[\e[32;95m\][seamless-mode]\[\e[0m\] \u@\h:\w$ '
    fi
    SEAMLESS_MODE_OPTS=$*
    if [ -z "$1" ]; then
        SEAMLESS_MODE_OPTS=''
    fi
    echo 'seamless mode ON'
    echo "seamless mode options: $SEAMLESS_MODE_OPTS"
    bind -x '"\C-t1":_seamless_complete'
    bind '"\C-t2": accept-line'
    bind '"\C-M":"\C-t1\C-t2"'
}


function seamless-mode-off() {
    echo 'seamless mode OFF'
    bind '"\C-M": accept-line'
    if [ -n "$_SEAMLESS_MODE_OLD_PS1" ]; then
        PS1=$_SEAMLESS_MODE_OLD_PS1
        unset _SEAMLESS_MODE_OLD_PS1
    fi

}

function seamless-mode-toggle() {
    if [ -n "$SEAMLESS_MODE_ON" ]; then
        unset SEAMLESS_MODE_ON
        echo seamless-mode-off
        seamless-mode-off
    else
        SEAMLESS_MODE_ON=1
        echo seamless-mode '-v'
        seamless-mode '-v'
    fi 
}    

bind -x '"\C-uu":seamless-mode-toggle'
echo 'seamless-mode-toggle: Press Ctrl-U, then U '

