# Deep cells

The primary function of deep cells is to describe data that is too big to fit in memory, by using a checksum-of-checksums approach. A deep cell has a checksum where the underlying value is itself a dict of checksums. Those checksums can either be of celltype "mixed" (DeepCell) or "bytes" (DeepFolderCell, FolderCell).

***IMPORTANT: This documentation section is a stub.***

(relevant tests are probably not that useful without explanation first. Integrate with "deep structures" in "Seamless explained".)
<!--
Intro:
- Deep cells
- DeepCell, DeepFolderCell, FolderCell

TODO: move/clone from "Deep structures" in "Seamless explained"
-->