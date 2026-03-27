# seamless-mode demo
# Shows: the two-step Enter interaction — first Enter transforms the command
# (prepends seamless-run), second Enter executes it. Also shows the toggle hotkey.

# --- Dependencies ---
Require "seamless-run"
Require "bash"

# --- Output ---
Output seamless-mode.gif

# --- Settings ---
Set Shell "bash"
Set Width 800
Set Height 420
Set FontSize 14
Set FontFamily "DejaVu Sans Mono"
Set Theme "Dracula"
Set WindowBar Colorful
Set Padding 8
Set TypingSpeed 80ms
Set Framerate 24

# --- Setup (hidden): source the binding script and enable seamless mode ---
Hide
Type "export SEAMLESS_CACHE=/tmp/TEST && mkdir -p /tmp/TEST && seamless-init && source $(which seamless-mode-bind.sh)"
Enter
Sleep 10s
Type "seamless-mode-bind"
Enter
Type "seamless-mode-on && clear"
Enter
Sleep 2s
Show

# --- Type a pipeline, press Enter: whole command is wrapped as seamless-run -c '...' ---
Sleep 500ms
Type "seq 10 | tac | awk -v l='Countdown:' '{print l, $1}' && sleep 5"
Sleep 1s
Enter
Sleep 2s

# --- The transformed command is now shown; press Enter again to run it ---
Enter
Sleep 8s

# --- Type a pipeline, press Enter: whole command is wrapped as seamless-run -c '...' ---
Sleep 500ms
Up
Sleep 1s
Up
Sleep 1s
Enter
Sleep 2s

# --- The transformed command is now shown; press Enter again to run it ---
Enter
Sleep 3s

# --- Toggle off with the hotkey (Ctrl-U then U) ---
Sleep 500ms
Ctrl+u
Sleep 100ms
Type "u"
Sleep 1s

# --- Prompt is restored ---
Sleep 1s

# --- Final pause before loop ---
Sleep 2s
