# Input data provenance

This directory contains the exact edge-list copies used by the checked
experiment results in `../results/`. Keeping the copies here makes the code
artifact independent of the parent `SubResearch` repository layout.

## Files

| File | Dataset | Input interpretation | SHA-256 |
| --- | --- | --- | --- |
| `email.txt` | Email-Eu-core | directed edge list; input arcs retained | `52583871255368570372333457E854951E7E85F30CAB4AA1AFC5F5CE3CC1D2F8` |
| `GrQc.txt` | ca-GrQc | undirected edge list; each deduplicated edge expanded into both arcs by the runner | `480B05A5578D3635581F397D2892191F99E4CA2BC724D1D12A38BFCAE13969B7` |

The upstream dataset pages are [email-Eu-core](https://snap.stanford.edu/data/email-Eu-core.html)
and [ca-GrQc](https://snap.stanford.edu/data/ca-GrQc.html). Both are part of
the [SNAP collection](https://snap.stanford.edu/data/), which asks users to
cite Jure Leskovec and Andrej Krevl, "SNAP Datasets: Stanford Large Network
Dataset Collection," 2014.

The files use whitespace-separated endpoint IDs. Blank lines and lines whose
first non-whitespace character is `#` are ignored by the loader. Node IDs are
remapped to contiguous internal IDs in first-seen order.

## Preprocessing performed by the runner

For Email-Eu-core, the loader retains each input arc and checks that the
normalized graph has 1,005 nodes and 25,571 arcs.

For ca-GrQc, the loader treats each input edge as undirected, removes duplicate
arcs, expands every remaining edge into both directions, and checks that the
normalized graph has 5,242 nodes and 28,980 arcs.

The source pages report 14,496 undirected ca-GrQc edges. The 28,980-arc count
in this artifact is the directed expansion used by the influence simulator.

The dataset-specific source citations listed by SNAP are Hao Yin, Austin R.
Benson, Jure Leskovec, and David F. Gleich, "Local Higher-Order Graph
Clustering," KDD 2017 for Email-Eu-core, and Jure Leskovec, Jon Kleinberg, and
Christos Faloutsos, "Graph Evolution: Densification and Shrinking Diameters,"
TKDD 2007 for ca-GrQc.

These transformations are part of the experiment definition. Do not replace
the files or change the topology convention without regenerating and
re-auditing the result files.

## Redistribution note

The files are included as convenience copies of the public network datasets
used by the parent experiment. The SNAP pages provide the authoritative
dataset descriptions and download links; they do not grant this artifact a
new blanket data license. Before publishing, verify the upstream attribution
and redistribution terms required by the venue or host. If redistribution is
not permitted, remove the raw copies from the public repository, retain this
provenance file, and update the README with approved download instructions and
replacement-file hashes.
