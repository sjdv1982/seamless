# Replay Mode Contract

Replay mode verifies that a crystallized `seamless.db` and companion bufferdir
are sufficient for a recipient script. The `seamless-share` harness configures
replay mode, launches the script in a subprocess, and serializes runtime events;
Seamless runtime paths enforce cache, materialization, remote-dispatch, and
write discipline.

V1 uses `SEAMLESS_REPLAY_MODE=1` plus explicit artifact, bufferdir,
authorization, driver-cache, remote, config, and event-file environment
variables. Runtime packages must not import `seamless_share`; they emit neutral
JSON Lines events through `seamless_transformer.replay_runtime`.

Reports are deterministic JSON with schema version `0.1.0`. The artifact
database and bufferdir must be byte-identical before and after replay.
