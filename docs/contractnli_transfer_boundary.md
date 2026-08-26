# ContractNLI transfer boundary

The adapter consumes only document-level entailment/contradiction/unknown
labels and evidence spans. It preserves document IDs, hypothesis IDs, source
hashes, and span offsets. ContractNLI labels are not executable rules and do
not provide gold-DMN execution outcomes; no transfer claim may rename them as
OE or AFS.
