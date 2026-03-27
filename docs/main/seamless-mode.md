# Seamless mode

## Automatically wrap the bash commands you type

![seamless-mode demo](seamless-mode.gif)

Seamless mode is an interactive shell feature that automatically wraps commands you type with `seamless-run`, giving you caching and reproducibility without changing how you work.

When seamless mode is on, pressing Enter no longer executes the command directly. Instead:

1. The command is transformed into a `seamless-run -c '...'` call — the entire command line, including any pipes, is quoted and passed as a shell string — and the modified command is shown in the shell.
2. You press Enter a second time to actually run it.

This two-step confirmation lets you see exactly what will be executed before committing. The `-c` form is what makes pipelines work: something like

```bash
seq 10 | tac | awk -v l='Countdown:' '{print l, $1} && sleep 5'
```

becomes a single cached transformation, without you having to hand-craft the quoting.

Commands that make no sense to wrap (like `cd`, `ls`, `rm`, editors, and package managers) are passed through unchanged and execute on the first Enter as normal.

## Setup

`seamless-mode-bind.sh` is installed alongside `seamless-transformer`. Source it in your shell to make the seamless-mode commands and hotkey available:

```bash
source $(which seamless-mode-bind.sh)
```

For permanent setup (so it is available every time you open a shell), see the [seamless-transformer README](api/seamless-transformer.md#setting-up-seamless-mode) for instructions specific to your environment manager (conda, venv, virtualenv, virtualenvwrapper).

## Usage

After sourcing `seamless-mode-bind.sh`, the following commands are available:

| Command | Effect |
|---------|--------|
| `seamless-mode-bind` | Registers all commands and the hotkey (called automatically on source) |
| `seamless-mode-on` | Turn seamless mode on |
| `seamless-mode-off` | Turn seamless mode off |
| `seamless-mode-toggle` | Toggle seamless mode on/off |

The toggle is also bound to a hotkey: **Ctrl-U, then U**.

```bash
$ seamless-mode-on
seamless mode ON
seamless mode options:
[seamless-mode] user@host:~$ seq 10 | tac | awk -v l='Countdown:' '{print l, $1}' && sleep 5   # press Enter...
[seamless-mode] user@host:~$ seamless-run -c 'seq 10 | tac | awk -v l='\''Countdown:'\'' '\''{print l, $1}'\'' && sleep 5'   # ...shown, press Enter again to run
```

Pass options to `seamless-run` via `seamless-mode-on`:

```bash
seamless-mode-on --stage mycluster
```

These options are forwarded to every `seamless-run` invocation while the mode is active.

## What gets wrapped

`seamless-run` is invoked only when the command is a plain executable call with file or directory arguments. Commands that are skipped include:

- Shell builtins and navigation: `cd`, `exit`, `source`, ...
- File operations: `ls`, `rm`, `mv`, `cp`, `mkdir`, ...
- Package managers: `pip`, `conda`, `mamba`, `apt`, ...
- Editors and interactive tools: `vim`, `nano`, `less`, `man`, ...
- The `seamless-*` commands themselves

Pipelines are handled: each stage is evaluated independently, and only stages that qualify are wrapped.

## Variable scope

`seamless-run` runs in a subprocess and only sees **environment variables** — not local shell variables. This means:

```bash
input=data.txt          # local variable — NOT visible to seamless-run
export input=data.txt   # environment variable — visible
```

With seamless mode on, `set -a` is active, so new variable assignments are automatically exported:

```bash
seamless-mode-on
input=data.txt          # now exported automatically
mycommand $input        # seamless-run can see $input
```

Variables that were local before `seamless-mode-on` was called are not retroactively exported.
