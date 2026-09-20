Prompt

Please read @seamless/cells-and-expressions-known-issues.md . I want you to reorganize the file. Make the following sections:
- Feature list
- Coordinated implementation change plans (or a reference to documents containing such plans) that are still to do
- Test set gaps
- Known bugs
- Misc thing to do

Subtasks stage 1: Design decisions (open or closed) need to be verified against the agentic contract docs to see if they are mentioned. If not, they need to be added to those docs. If they are really open decisions, put them in an appendix at the end. Otherwise, remove them from the code.

Subtasks stage 2: The agentic code doc for each feature needs to be analyzed for consistency  and completeness. Do the same for each pair of new agentic code docs. Only  gaps/inconsistencies need to be reported: if obvious, fix them right away. Finally, at the end. fire up a special Opus high subagent that does a final pass on all agentic contract docs (not just the new ones).

Subtasks stage 3: For the agentic code doc for each feature, it needs to be compared against the test set for errors in the test and coverage gaps. Report gaps and errors (in a special section in the reorganized doc) but don't fix them.

For these subtasks, I want you to fire up a Sonnet subagent per subtask (not per stage), grouping small related subtasks together. This subagents should receive its context from you. Where needed, it is allowed read the docs referenced in @seamless/cells-and-expressions-known-issues.md  , agentic contract docs, the test set, and only if really needed, the implementation code.