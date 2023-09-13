function _export_variables() {
    if [ -z "$_MY_READONLYVARS" ]; then
        echo 'Exporting local shell variables as environment variables...'
        export _MY_READONLYVARS=$(readonly -p | python -c '''
import sys
result = ""
for l in sys.stdin.readlines():
    l = l.strip()
    eq = l.find("=")
    if eq == -1: continue
    sp = l[:eq].rfind(" ")
    if sp == -1: 
        v = l[:eq]
    else: 
        v = l[sp+1:eq]
    result += v + " "
print(result.strip())
''')
        _MY_EXPORT_VARS=$( declare -p | python -c '''
import sys, os
readonlyvars = os.environ["_MY_READONLYVARS"].split()
ok = True
for l in sys.stdin.readlines():
    l = l.strip()
    ll = l.split()
    if len(ll) < 3 or ll[0] != "declare":
        if ok: print(l)
        continue
    v = ll[2]
    eq = v.find("=")
    if eq == -1:
        eq = len(v)
    varname = v[:eq]
    ok = True
    if varname.startswith("_") or varname in readonlyvars:
        ok = False
    if ok: print(l)
''')        
        eval "$_MY_EXPORT_VARS" >& /dev/null
    fi    
}

function _expand_variables () {
    READLINE_LINE=$(echo "$READLINE_LINE" | envsubst)
}

function _add_history () {
    UNEXPANDED_READLINE_LINE=$READLINE_LINE
    history -s $READLINE_LINE
}


function _seamless_complete() {    
    PREV_READLINE_LINE=$READLINE_LINE
    READLINE_LINE=$(_seamlessify $READLINE_LINE @@@ $SEAMLESS_MODE_OPTS)
    SEAMLESS_READLINE_LINE="$READLINE_LINE"
    if [ "$SEAMLESS_READLINE_LINE" == "$PREV_READLINE_LINE" ]; then
        # seamlessify did nothing. Undo the previous shell-expand-line
        READLINE_LINE="$UNEXPANDED_READLINE_LINE"
    else
        # block execution
        BLOCKED_READLINE_LINE="$READLINE_LINE"
        READLINE_LINE=""
    fi

}

function _restore_line() {
    if [ "$SEAMLESS_READLINE_LINE" != "$PREV_READLINE_LINE" ]; then
        READLINE_LINE="$BLOCKED_READLINE_LINE"
    fi    
}
function seamless-mode-on() {
    SEAMLESS_MODE_ON=1
    ###_export_variables # does not work properly...
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
    bind -x '"\C-u8": _expand_variables'
    bind -x '"\C-u1":_seamless_complete'
    bind '"\C-u2": accept-line'
    bind -x '"\C-u7":_restore_line'
    bind '"\C-M":"\C-u9\C-u8\C-u1\C-u2\C-u7\e[F"'
}


function seamless-mode-off() {
    echo 'seamless mode OFF'
    unset SEAMLESS_MODE_ON
    bind '"\C-M": accept-line'
    if [ -n "$_SEAMLESS_MODE_OLD_PS1" ]; then
        PS1=$_SEAMLESS_MODE_OLD_PS1
        unset _SEAMLESS_MODE_OLD_PS1
    fi

}

function seamless-mode-toggle() {
    if [ -n "$SEAMLESS_MODE_ON" ]; then
        READLINE_LINE=""
        echo seamless-mode-off
        seamless-mode-off
    else        
        echo seamless-mode-on '-v'
        seamless-mode-on '-v'
    fi 
}    

function seamless-mode() {    
    bind -x '"\C-u3":seamless-mode-toggle'
    bind '"\C-u4": accept-line'
    bind '"\C-uu":"\C-u3\C-u4"'
    echo 'seamless mode is now available'
    echo 'You can enable it or disable it with the following commands:'
    echo ''
    echo 'seamless-mode-on, seamless-mode-off, seamless-mode-toggle'
    echo 'seamless-mode-toggle has been bound to a hotkey: Press Ctrl-U, then U'
    echo ''
    echo 'When seamless-mode is on, all commands will be executed using /bin/seamless'
    echo '/bin/seamless has only access to environment variables (e.g. "export a=1"),'
    echo '  not to local shell variables (e.g. "a=1") '
    echo 'From now on, new local shell variables will be exported.'
    set -a
}
