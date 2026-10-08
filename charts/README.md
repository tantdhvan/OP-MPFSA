# Chart pipeline

`plot_fair_kim_results.py` is a standalone Matplotlib pipeline for the fair
k-IM artifact. It reads the normalized CSV files under `../results/` and does
not import code from the parent research repository.

Run from the artifact root:

```bash
python charts/plot_fair_kim_results.py --dataset email --prefix email
python charts/plot_fair_kim_results.py --dataset grqc --prefix grqc
```

The default input directory is `../results` relative to this directory and the
default output directory is this directory. Use `--input-dir` and `--outdir`
when working with a separate result snapshot. The script validates the
dataset name, required columns, algorithm set, and requested budgets before
plotting.

The generated metrics are:

- objective value `f(x)`;
- `Number of queries`, defined as value-oracle calls without multiplying by
  decision-bank Monte Carlo size; and
- `Peak memory (MB)`, defined as the Python `tracemalloc` algorithm-phase
  peak, not full process RSS.

Each dataset output contains a PDF bundle with a shared legend and three
metric pages, a compact three-panel PNG, individual metric PNGs, a legend PNG,
a long-format summary CSV, and a JSON provenance manifest. The summary keeps
the objective evaluation-bank standard error but does not draw run-to-run
confidence bands because the artifact has one deterministic run per algorithm
and budget.

The generated files currently committed in this directory are the figures
used by the manuscript revision. Re-running the script overwrites files with
the same prefix, so preserve a copy or use a new output directory when
creating a new experiment snapshot.
