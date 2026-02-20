## Deep checksums: what they buy you (non-jargon)

Deep checksums let you give an *identity* to a large, structured dataset—without bundling it into one big blob.

Think: a dataset as a tree (folders, nested dicts/lists, records). A deep checksum is a fingerprint of the whole tree that also fingerprints every leaf. The important part is what that enables:

- **Precise definition without local presence**:
  You can say “this computation’s input is *exactly this dataset*” even if it’s hundreds of GB and not stored locally.
- **Separation of definition and materialization**:
  The computation can be specified, cached, scheduled, compared, and reasoned about using identities. The bytes only need to be fetched when/where execution actually happens.
- **Verifiability**:
  When data is fetched from remote storage, it can be verified against the checksum identity.
- **Partial transfer (when supported)**:
  Only missing pieces need to be moved to a machine that will execute the step.

## What “precisely define” means (recommended phrasing)

“Precisely define” means you can fully specify *what* you will compute and *exactly which data* it refers to, immutably, using content-based identifiers—without requiring that the data be read, loaded, or even present locally at definition time.

## Analogy

- A filename is a *pointer* that can change meaning.
- A deep checksum is a *commit hash* for data: it names a specific, immutable version of a structured dataset.

