# Reproducible code artifact for fair monotone k-submodular streaming

This directory is a self-contained experiment artifact for the manuscript
`Streaming Algorithms for Monotone k-Submodular Maximization under Fairness
Constraints`.

It is intended to be copied to a separate public repository and linked from
the manuscript. It contains the exact runner, input edge lists, result files,
plotting pipeline, and currently generated figures used for the exploratory
k-IM experiments in Section 5.

The artifact snapshot corresponds to the revision state on 2026-10-08. The
experiments are exploratory evidence for implementation-level behavior. They
are not a statistical comparison over repeated independent runs and they do
not validate the approximation theorems.

## Contents

```text
.
|-- README.md
|-- LICENSE
|-- CITATION.cff
|-- requirements.txt
|-- requirements-lock.txt
|-- run_fair_kim.py
|-- run_fair_kim.slurm.sh
|-- validate_results.py
|-- data/
|   |-- README.md
|   |-- email.txt
|   `-- GrQc.txt
|-- results/
|   |-- run_details.csv
|   `-- grqc/run_details.csv
`-- charts/
    |-- plot_fair_kim_results.py
    |-- requirements.txt
    |-- email.pdf, email_panel.png, ...
    |-- grqc.pdf, grqc_panel.png, ...
    `-- generated manifests and summary CSVs
```

The two result CSVs contain 32 rows each: four algorithms evaluated at eight
budgets. The files under `charts/` are generated outputs kept in the artifact
so that the manuscript figures can be inspected without rerunning the
experiments.

## Software requirements

- Python 3.10 or newer.
- SciPy for the balanced-label linear program used by MPFSA.
- Matplotlib for chart generation.

Install the dependencies from the artifact root:

```bash
python -m pip install -r requirements.txt
```

For the tested environment, use `requirements-lock.txt` instead. It records
Python 3.12.5, Matplotlib 3.10.1, and SciPy 1.15.2.

```bash
python -m pip install -r requirements-lock.txt
```

The repository-level `requirements.txt` includes both the runner and plotting
dependencies. `charts/requirements.txt` lists the plotting dependency alone
for users who only want to regenerate figures.

## Reproduce the experiment

Run these commands from the artifact root:

```bash
python run_fair_kim.py --dataset email --output-dir results/recomputed
python run_fair_kim.py --dataset grqc --output-dir results/recomputed
```

The first command writes `results/recomputed/run_details.csv`. The second
writes `results/recomputed/grqc/run_details.csv`. Existing files at the target
paths are replaced; using a separate output directory protects the checked
CSV snapshot under `results/`.
The default command line settings reproduce the paper protocol:

- algorithms: Fair-Greedy, Fair-Threshold, OPFSA, and MPFSA;
- budgets: `B = 9, 12, 15, 18, 21, 24, 27, 30`;
- number of labels: `k = 3`;
- per-label quotas: `ell_i = 3` and `u_i = 10`;
- accuracy parameter: `epsilon = 0.1`;
- decision bank: 100 Monte Carlo worlds;
- final evaluation bank: 1,000 Monte Carlo worlds;
- deterministic random seed: 42.

The runner also supports bounded diagnostic runs:

```bash
python run_fair_kim.py --dataset email --smoke
python run_fair_kim.py --dataset grqc --algorithms MPFSA --budgets 9 12 \
  --output-dir results/diagnostic
```

The `--smoke` option runs only Fair-Greedy at `B=9`. These diagnostic modes
are not the full manuscript experiment. Do not use them to replace the
checked result files without documenting the changed settings.

Validate the frozen result files without running any algorithm:

```bash
python validate_results.py
python validate_results.py --results-dir results --dataset email
```

The validator checks the 4 x 8 algorithm-budget grid, dataset sizes, quota
metadata, support sizes, access-model labels, pass semantics, Monte Carlo
settings, seed, and finite numeric metrics.

### Slurm execution

For a substantive grid on a cluster, submit the tracked Slurm script rather
than running the grid on a login node:

```bash
OUTPUT_DIR=results/recomputed DATASET=email sbatch run_fair_kim.slurm.sh
OUTPUT_DIR=results/recomputed DATASET=grqc sbatch run_fair_kim.slurm.sh
```

The script requests one CPU and 8 GB of memory for up to eight hours. Override
the Python executable with `PYTHON=/path/to/python` if needed. Record the job
ID and inspect both the `.out` and `.err` files before treating a new result
file as complete.

## Experimental protocol

The runner uses independent Weighted-Cascade live-edge worlds for the three
labels, with

```text
p(u,v) = 1 / indegree(v).
```

The objective is expected union spread across the label-specific cascades.
The stream order is a deterministic random permutation generated with seed
42 and is shared by all algorithms and budgets on a dataset.

Email-Eu-core is loaded as a directed graph using its input arcs. ca-GrQc is
loaded as an undirected graph: node IDs are remapped, duplicate undirected
edges are removed, and each remaining undirected edge is expanded into both
directions. The expected normalized sizes are checked by the runner:

| Dataset | Topology used by the runner | Nodes | Arcs after loading |
| --- | --- | ---: | ---: |
| Email-Eu-core | directed input | 1,005 | 25,571 |
| ca-GrQc | undirected, then expanded | 5,242 | 28,980 |

Each algorithm is run exactly once for each budget. The final objective is
evaluated after the algorithm finishes using the separate 1,000-world
evaluation bank. Therefore, the reported standard error is Monte Carlo
sampling error in the evaluation bank, not run-to-run uncertainty.

## Algorithms and access semantics

The implementation includes the two offline baselines and the two streaming
algorithms used in the manuscript:

| Algorithm | Access model | Pass or scan interpretation |
| --- | --- | --- |
| Fair-Greedy | offline | `B` full offline scans, one per greedy selection |
| Fair-Threshold | offline lazy priority queue | `NA`; lazy refreshes use arbitrary access and are not replayable stream passes |
| OPFSA | one-pass fixed-order | one scan of the fixed stream order |
| MPFSA | replayable fixed-order | decreasing-threshold replay passes |

The `passes` column is therefore a mixed metadata field. It is comparable as a
streaming-pass count only for OPFSA and MPFSA. Fair-Greedy's value is included
to describe its offline scan work; Fair-Threshold is deliberately recorded as
`NA`.

## Metric definitions

### Objective value

`objective` is the mean union spread over the separate final evaluation bank.
`evaluation_se` is the standard error of that mean over 1,000 evaluation
worlds.

### Number of queries

`queries` is the number of value-oracle calls made by the algorithm. One call
evaluates the requested marginal value using the fixed decision bank. The
count is not multiplied by the decision-bank size (`MC=100`). The final
evaluation bank is used only after the algorithm has completed and is not
included in `queries`.

This is the single query convention used by the manuscript and all chart
outputs.

### Peak memory (MB)

`peak_memory_mb` is measured with Python `tracemalloc` around the algorithm
phase. It is not full process-peak RSS and does not include every native
allocation, such as memory allocated inside SciPy. The metric is retained as
an implementation-level Python allocation measurement and must not be
interpreted as a complete machine-memory measurement.

`runtime_seconds` is also recorded in the CSV but is machine-dependent and is
not one of the manuscript's three plotted criteria.

## Result file schema

The CSV files use the following fields:

| Field | Meaning |
| --- | --- |
| `dataset` | Dataset name used in the manuscript |
| `n`, `m` | Loaded node and arc counts |
| `topology` | `directed` or `undirected-expanded` |
| `algorithm` | Algorithm name |
| `access_model` | Offline or streaming access label |
| `B`, `k` | Total budget and number of labels |
| `lower`, `upper` | Semicolon-separated per-label quotas |
| `objective`, `evaluation_se` | Final evaluation mean and standard error |
| `queries` | Value-oracle call count, without MC multiplication |
| `passes` | Scan/pass metadata described above |
| `runtime_seconds` | Wall-clock algorithm time on the generating machine |
| `peak_memory_mb` | Python-traced algorithm-phase peak memory |
| `support_size` | Number of selected supports after completion |
| `label_counts` | Semicolon-separated final label counts |
| `decision_MC`, `evaluation_MC` | Decision and final evaluation bank sizes |
| `seed` | Random seed used for stream order and algorithm randomness |

All checked rows satisfy `support_size == B` and every label count lies in
`[3, 10]`.

## Recreate the figures

The plotting script reads the normalized result CSVs and writes output into
`charts/` by default:

```bash
python charts/plot_fair_kim_results.py --dataset email --prefix email
python charts/plot_fair_kim_results.py --dataset grqc --prefix grqc
```

Each dataset produces:

- `<prefix>.pdf`: a four-page bundle containing the shared legend followed by
  objective, query, and memory pages;
- `<prefix>_panel.png`: the compact three-panel figure;
- `<prefix>_objective.png`, `<prefix>_queries.png`, and
  `<prefix>_memory.png`: individual metric panels;
- `<prefix>_legend.png`: the standalone legend;
- `<prefix>_plot_summary.csv`: plotting-ready long-format values; and
- `<prefix>_plot_manifest.json`: provenance and metric-definition metadata.

The query and memory panels use logarithmic y-axes. The objective panel uses a
linear y-axis. The three metric panels have equal canvas dimensions; the
standalone legend is exported separately with a narrower tight bounding box.
Markers, labels, colors, and metric names are shared across the two datasets.

## Reproducibility limitations

1. There is one deterministic run per algorithm and budget. No run-to-run
   confidence interval or statistical significance claim is supported.
2. `evaluation_se` quantifies only sampling error in the final evaluation
   bank.
3. Fair-Threshold's low query count should not be described as a streaming
   pass advantage because its lazy priority queue uses arbitrary-access
   refreshes.
4. The memory panel reports Python-traced algorithm-phase allocations, not
   full RSS.
5. Runtime values depend on hardware, Python version, SciPy version, and
   system load. They are retained for provenance but are not used in the
   manuscript chart.
6. Changing the seed, Monte Carlo bank sizes, graph preprocessing, or quota
   settings creates a new experiment and should be recorded separately.

## Data provenance

The exact input copies used for the checked results are included in `data/`.
See [`data/README.md`](data/README.md) for file hashes, preprocessing, and
upstream URLs, attribution, and redistribution notes.

## Citation and manuscript link

When this directory is uploaded as a separate repository, replace the
repository URL in the manuscript's Data availability and Code availability
statements with the public repository link. Until then, the parent draft keeps
the local artifact as the source of the figures and result files.

Please cite the associated manuscript:

> Dung T. Pham, Tan D. Tran, and Canh V. Pham. *Streaming Algorithms for
> Monotone k-Submodular Maximization under Fairness Constraints*. Manuscript,
> 2026.

The original code and documentation are released under the MIT License; see
[`LICENSE`](LICENSE). The bundled datasets are not relicensed by this
artifact and remain subject to their upstream terms. The machine-readable
citation record is in [`CITATION.cff`](CITATION.cff).

## Artifact status

This is a revision-stage artifact. The code and results are frozen for the
reported exploratory comparison unless a new experiment is explicitly
authorized. Any future rerun should preserve the existing CSVs, use a new
output location or commit, and record the changed environment and parameters.
