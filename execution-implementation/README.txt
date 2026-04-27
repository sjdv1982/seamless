Today (27th of April) the massive implementation of execution records was finished.

1. Original document: ../conversation/records/execution-records-implementation.md
2. Code review by Claude: ./review.md
3. Analysis of code paths that are triggered anyway: ./code-paths.md

Codex did the implementation, and Claude confirmed that it is essentially complete.
Roadmap:

Complete architecture (DONE) and no obvious bugs for common cases are the guidelines here.

A. Based on 1. and 2., finalize the implementation.
Decide what minimal records are to be kept even if record mode is off
B. Do regression tests, guided by 3.
C. Add documentation, clearly marking it as EXPERIMENTAL
D. Carefully run some manual tests. 
