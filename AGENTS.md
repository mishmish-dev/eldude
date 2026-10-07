# Working in Eldude

Start with [docs/index.md](docs/index.md), the task-oriented documentation and project map. Open the relevant chapter or component and its tests; follow cross-references when a rule depends on another topic.

The [implementation file map](tools/README.md#file-map) identifies code and tests. The [editing guide](docs/index.md#editing-and-checking) identifies authoritative sources and generated files. Use the [root README checks](README.md#checks) to verify changes.

Preserve numbered specification clauses and existing anchors. Distinguish normative language contracts from the experimental implementation's supported subset.

For every new language or library feature, write small `.eld` acceptance programs first and run them through the source parser, checker, and interpreter. Set expected results from the language contract, then implement until the programs work. Add rejection programs for relevant ownership, lifetime, effect, and constraint boundaries, and verify the intended diagnostic. Keep these programs in the example corpus and its tests; Python-only checks or `pending` examples do not establish feature completion.
