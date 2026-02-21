## FAIR and content identity: locators vs identifiers

### The distinction

FAIR's "persistent identifiers" (F1) are **persistent locators**: they guarantee that a reference won't break, not that the content it points to won't change. The FAIR spec explicitly leaves mutability to the data provider's policy.

- A UniProt ID (P53_HUMAN) is a locator: it points to the current best knowledge about human p53. The sequence behind it can change between releases.
- A DOI is a locator: it points to a publication slot that will always resolve.
- A checksum is an **identity**: it names exactly one immutable piece of content, regardless of where it's stored.

### Why this matters for computational science

For physical experiments, locators are fine: "I used the reagent from this supplier" is sufficient provenance. But for computation, the inputs *are* the experiment. If the input changes, the computation is a different computation.

A scientist who reports "I ran BLAST on P53_HUMAN" has not fully specified their computation. A scientist who reports "I ran BLAST (code checksum `x`) on sequence checksum `y`, which I obtained from UniProt P53_HUMAN on 2025-01-15" has.

### How Seamless relates to FAIR

Seamless and FAIR are complementary, not competing:

- **FAIR** answers: "how do I *find* data?" (persistent locators, metadata, access protocols)
- **Seamless** answers: "how do I *know* it's the same data?" (content-addressed checksums)

In practice:
- Use FAIR locators as metadata (findability, discoverability, citation)
- Use checksums as identity (reproducibility, caching, federation)
- Record both: "I found human p53 via UniProt (P53_HUMAN, release 2025_01), which at that time had sequence checksum `a7f3b2...`, and my analysis of that checksum produced result checksum `c4d8e1...`"

### Guidance for agents

When a user's pipeline reads from an external database (UniProt, PDB, GenBank, etc.):
- The *fetch* is outside code: resolve the locator, obtain the content, checksum it
- The *computation* uses the checksum as input, never the locator
- Record the locator as provenance metadata, not as a computational dependency
- If the upstream database updates, the old checksum still names the old content, and the old result remains valid for that exact input
