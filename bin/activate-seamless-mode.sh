function _add_history () {
    UNEXPANDED_READLINE_LINE=$READLINE_LINE
    history -s $READLINE_LINE
}


function _seamless_complete() {    
    PREV_READLINE_LINE=$READLINE_LINE
    READLINE_LINE=$(_seamlessify $READLINE_LINE @@@ $SEAMLESS_MODE_OPTS)
    SEAMLESS_READLINE_LINE=$READLINE_LINE
    if [ "$SEAMLESS_READLINE_LINE" == "$PREV_READLINE_LINE" ]; then
        # seamlessify did nothing. Undo the previous shell-expand-line
        READLINE_LINE=$UNEXPANDED_READLINE_LINE
    else
        history -s $READLINE_LINE
        READLINE_LINE=""
    fi

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
    bind -x '"\C-u9":_add_history'
    bind '"\C-u8": shell-expand-line'
    bind -x '"\C-u1":_seamless_complete'
    bind '"\C-u2": accept-line'
    bind '"\C-M":"\C-u9\C-u8\C-u1\C-u2\e[A"'
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

bind -x '"\C-u3":seamless-mode-toggle'
bind '"\C-u4": accept-line'
bind '"\C-uu":"\C-u3\C-u4"'
echo 'seamless-mode-toggle: Press Ctrl-U, then U '

