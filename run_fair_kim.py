"""Single-run k-topic IC experiment for the fair streaming draft.

The two edge lists are bundled under ``data/`` so this artifact can be cloned
and run independently of the parent research repository. Each topic uses an
independent Weighted-Cascade live-edge world
with p(u,v)=1/indegree(v). The objective is expected union spread across
topics. One common decision bank (MC=100) and one separate evaluation bank
(MC=1000) are shared across algorithms and budgets.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import math
import random
import statistics
import time
import tracemalloc
from collections import deque
from pathlib import Path

try:
    from scipy.optimize import linprog
except ImportError as exc:  # pragma: no cover - environment check
    raise SystemExit("This runner needs the repository Python environment with SciPy.") from exc


HERE = Path(__file__).resolve().parent
EDGE_FILE = HERE / "data" / "email.txt"
GRQC_FILE = HERE / "data" / "GrQc.txt"
DEFAULT_OUTPUT_DIR = HERE / "results"
K = 3
LOWER = (3, 3, 3)
UPPER = (10, 10, 10)
BUDGETS = (9, 12, 15, 18, 21, 24, 27, 30)
MC = 100
FINAL_MC = 1000
EPS = 0.1
SEED = 42


def load_graph(path: Path, undirected=False, expected_size=None):
    edges = []
    remap = {}
    seen = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2:
            raise ValueError(f"malformed edge at line {line_no}")
        source_raw, target_raw = map(int, fields[:2])
        for node in (source_raw, target_raw):
            if node not in remap:
                remap[node] = len(remap)
        u, v = remap[source_raw], remap[target_raw]
        for arc in ((u, v), (v, u)) if undirected else ((u, v),):
            if arc not in seen:
                seen.add(arc)
                edges.append(arc)
    n = len(remap)
    indegree = [0] * n
    outgoing = [[] for _ in range(n)]
    for u, v in edges:
        outgoing[u].append(v)
        indegree[v] += 1
    if expected_size and (n, len(edges)) != expected_size:
        raise ValueError(f"unexpected graph size: n={n}, m={len(edges)}; expected {expected_size}")
    return n, edges, outgoing, indegree


def sample_outgoing(n, edges, indegree, rng):
    sampled = [[] for _ in range(n)]
    for u, v in edges:
        if indegree[v] and rng.random() < 1.0 / indegree[v]:
            sampled[u].append(v)
    return sampled


def reach_bits(outgoing, source):
    seen = 1 << source
    queue = [source]
    for u in queue:
        for v in outgoing[u]:
            bit = 1 << v
            if not seen & bit:
                seen |= bit
                queue.append(v)
    return seen


class Banks:
    def __init__(self, n, edges, outgoing, indegree):
        self.n, self.edges, self.outgoing, self.indegree = n, edges, outgoing, indegree
        print(f"Building decision live-edge bank: MC={MC}, k={K}", flush=True)
        rng = random.Random(SEED)
        # reach[topic][trial][source] is a Python-int bitset.
        self.reach = []
        for topic in range(K):
            topic_trials = []
            for _ in range(MC):
                world = sample_outgoing(n, edges, indegree, rng)
                topic_trials.append([reach_bits(world, s) for s in range(n)])
            self.reach.append(topic_trials)
        print(f"Building final evaluation bank: MC={FINAL_MC}, k={K}", flush=True)
        # Store only live arcs; the input graph itself is shared.
        self.eval_worlds = [
            [sample_outgoing(n, edges, indegree, rng) for _ in range(K)]
            for _ in range(FINAL_MC)
        ]


class State:
    def __init__(self, banks):
        self.banks = banks
        self.assignment = {}  # support -> 1-based topic label
        self.counts = [0] * K
        self.union = [0] * MC
        self.queries = 0

    @property
    def size(self):
        return len(self.assignment)

    def extendable(self, label):
        j = label - 1
        if self.counts[j] >= UPPER[j]:
            return False
        load = sum(max(self.counts[i], LOWER[i]) for i in range(K))
        return load + int(self.counts[j] >= LOWER[j]) <= self.banks.n and load + int(self.counts[j] >= LOWER[j]) <= self.budget

    def set_budget(self, budget):
        self.budget = budget

    def extendable_labels(self, e):
        if e in self.assignment or self.size >= self.budget:
            return []
        return [i + 1 for i in range(K) if self.extendable(i + 1)]

    def marginals(self, e, labels=None, base_union=None):
        labels = list(range(1, K + 1)) if labels is None else list(labels)
        union = self.union if base_union is None else base_union
        result = {i: 0.0 for i in labels}
        for i in labels:
            reach = self.banks.reach[i - 1]
            result[i] = sum((reach[t][e] & ~union[t]).bit_count() for t in range(MC)) / MC
        self.queries += len(labels)
        return result

    def add(self, e, label):
        if e in self.assignment:
            raise ValueError("support already assigned")
        self.assignment[e] = label
        self.counts[label - 1] += 1
        reach = self.banks.reach[label - 1]
        for t in range(MC):
            self.union[t] |= reach[t][e]

    def rebuild(self):
        self.union = [0] * MC
        self.counts = [0] * K
        for e, label in self.assignment.items():
            self.counts[label - 1] += 1
            reach = self.banks.reach[label - 1]
            for t in range(MC):
                self.union[t] |= reach[t][e]

    def value(self):
        return sum(x.bit_count() for x in self.union) / MC


def feasible_extension_load(counts):
    return sum(max(counts[i], LOWER[i]) for i in range(K))


def complete(state, buffer, budget):
    """Apply the manuscript's deterministic buffer completion procedure."""
    state.set_budget(budget)
    targets = [max(state.counts[i], LOWER[i]) for i in range(K)]
    remaining = budget - sum(targets)
    for i in range(K):
        add = min(remaining, UPPER[i] - targets[i])
        targets[i] += add
        remaining -= add
    used = set(state.assignment)
    for i in range(K):
        while state.counts[i] < targets[i]:
            e = next((v for v in buffer if v not in used), None)
            if e is None:
                raise ValueError("completion buffer lacks an unused support")
            state.add(e, i + 1)
            used.add(e)
    if state.size != budget or any(not LOWER[i] <= state.counts[i] <= UPPER[i] for i in range(K)):
        raise AssertionError("completion returned an infeasible assignment")


def eval_final(banks, assignment):
    seeds = [[e for e, i in assignment.items() if i == topic + 1] for topic in range(K)]
    values = []
    for world in banks.eval_worlds:
        union = 0
        for topic in range(K):
            seen = 0
            q = deque(seeds[topic])
            while q:
                e = q.popleft()
                bit = 1 << e
                if seen & bit:
                    continue
                seen |= bit
                for v in world[topic][e]:
                    if not seen & (1 << v):
                        q.append(v)
            union |= seen
        values.append(union.bit_count())
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return mean, se


def fair_greedy(banks, n, order, budget):
    """Offline greedy baseline.

    The loop performs one full-order scan per greedy selection. Record those
    B scans explicitly; this is an offline scan count, not a streaming-pass
    claim.
    """
    s = State(banks); s.set_budget(budget)
    while s.size < budget:
        best = None
        best_gain = -1.0
        for e in order:
            if e in s.assignment:
                continue
            labels = s.extendable_labels(e)
            if not labels:
                continue
            gs = s.marginals(e, labels)
            for i in labels:
                if gs[i] > best_gain or (gs[i] == best_gain and (best is None or (e, i) < best)):
                    best_gain, best = gs[i], (e, i)
        if best is None:
            break
        s.add(*best)
    complete(s, order[: min(n, 2 * budget)], budget)
    return s, budget


def fair_threshold(banks, n, order, budget):
    """Offline lazy-priority-queue baseline.

    Its heap performs arbitrary-access lazy refreshes rather than replayable
    stream passes, so the pass field is deliberately reported as ``NA``.
    """
    s = State(banks); s.set_budget(budget)
    heap = []
    updates = {}
    for e in order:
        gs = s.marginals(e, range(1, K + 1), [0] * MC)
        for i in range(1, K + 1):
            heapq.heappush(heap, (-gs[i], e, i))
            updates[(e, i)] = 0
    # Lazy Fair-Threshold priority queue from Zhu--Basu--Pavan, with each
    # stale marginal refreshed at most ceil(eps^{-1} log(B/(2 eps))) times.
    update_cap = max(1, math.ceil(math.log(budget / (2 * EPS)) / EPS))
    while heap and s.size < budget:
        neg_tau, e, i = heapq.heappop(heap)
        if e in s.assignment or i not in s.extendable_labels(e):
            continue
        tau = -neg_tau
        updates[(e, i)] += 1
        gain = s.marginals(e, [i])[i]
        if gain + 1e-12 >= (1 - EPS) * tau:
            s.add(e, i)
            continue
        if updates[(e, i)] <= update_cap:
            heapq.heappush(heap, (-gain, e, i))
    complete(s, order[: min(n, 2 * budget)], budget)
    return s, "NA"


def circuit_blockers(state, e, label):
    counts = state.counts
    i = label - 1
    if counts[i] == UPPER[i]:
        return [v for v, j in state.assignment.items() if j == label]
    rank = state.budget - sum(LOWER)
    excess = sum(max(0, counts[j] - LOWER[j]) for j in range(K))
    if excess == rank and counts[i] >= LOWER[i]:
        return [v for v, j in state.assignment.items() if j == label or counts[j - 1] > LOWER[j - 1]]
    return []


def opfsa(banks, n, order, budget):
    eta = EPS
    cstar = 1.0 + math.sqrt(2.0)
    buffer = order[: min(n, 2 * budget)]
    m = 0.0
    lanes = {}
    singleton_queries = 0
    probe = State(banks)
    probe.set_budget(budget)
    for e in order:
        singleton_labels = probe.extendable_labels(e)
        singleton_queries += len(singleton_labels)
        if not singleton_labels:
            sing = 0.0
        else:
            sing = max(sum(banks.reach[i - 1][t][e].bit_count() for t in range(MC)) / MC for i in singleton_labels)
        m = max(m, sing)
        if m > 0:
            lo = math.ceil(math.log(m, 1 + eta) - 1e-12)
            hi = math.floor(math.log(budget * m / eta, 1 + eta) + 1e-12)
            active = set(range(lo, hi + 1))
            lanes = {j: lanes.get(j) for j in active}
            for j in active:
                if lanes[j] is None:
                    archive = State(banks); archive.set_budget(budget)
                    live = State(banks); live.set_budget(budget)
                    lanes[j] = (archive, live, {})
        for j, (archive, live, weights) in lanes.items():
            v = (1 + eta) ** j
            accepted = []
            for i in range(1, K + 1):
                blockers = circuit_blockers(live, e, i)
                can_insert = live.extendable(i)
                if not can_insert and not blockers:
                    continue
                a = archive.marginals(e, [i])[i]
                theta = min((weights[(b, live.assignment[b])] for b in blockers), default=0.0)
                if a >= cstar * theta + eta * v / budget:
                    accepted.append((a, i, blockers))
            if accepted:
                a, i, blockers = max(accepted, key=lambda item: (item[0], -item[1]))
                archive.add(e, i)
                weights[(e, i)] = a
                if blockers:
                    victim = min(blockers, key=lambda b: (weights[(b, live.assignment[b])], b))
                    del live.assignment[victim]
                    live.rebuild()
                live.add(e, i)
    if not lanes:
        result = State(banks); result.set_budget(budget)
        complete(result, order[:min(n, 2 * budget)], budget)
        result.queries = singleton_queries
        return result, 1
    best_state, best_value = None, -1.0
    total_queries = singleton_queries
    for archive, live, weights in lanes.values():
        total_queries += archive.queries
        candidate = State(banks); candidate.set_budget(budget)
        candidate.assignment = live.assignment.copy(); candidate.counts = live.counts.copy(); candidate.union = live.union.copy()
        complete(candidate, order[:min(n, 2 * budget)], budget)
        score = candidate.value()
        if score > best_value:
            best_state, best_value = candidate, score
    best_state.queries = total_queries
    return best_state, 1


def balanced_distribution(values):
    labels = list(values)
    a = [values[i] for i in labels]
    m = len(labels)
    c = 1.0 if m == 1 else ((1 + math.sqrt(2)) / 2 if m == 2 else 2 - 1 / (m - 1))
    amax = max(a)
    # Feasible-label LP for the two balanced-label inequalities in Lemma 4.6.
    A, b = [], []
    A.append([-c * x for x in a]); b.append(-amax)
    for h in range(m):
        row = [-c * x for x in a]
        row[h] -= amax + a[h]
        A.append(row); b.append(-(amax + a[h]))
    result = linprog([0.0] * m, A_ub=A, b_ub=b, A_eq=[[1.0] * m], b_eq=[1.0], bounds=[(0.0, 1.0)] * m, method="highs")
    if not result.success:
        raise RuntimeError(f"balanced-label LP failed: {result.message}")
    return labels, result.x


def mpfsa(banks, n, order, budget, seed):
    state = State(banks); state.set_budget(budget)
    buffer = order[: min(n, 2 * budget)]
    M = 0.0
    for e in order:
        gs = state.marginals(e, range(1, K + 1), [0] * MC)
        if state.extendable_labels(e): M = max(M, max(gs.values()))
    if M <= 0:
        complete(state, buffer, budget)
        return state, 1
    x = 1.0 - EPS
    tau = M
    passes = 1
    rng = random.Random(seed)
    while tau >= EPS * M / budget and state.size < budget:
        passes += 1
        for e in order:
            labels = state.extendable_labels(e)
            if not labels: continue
            gs = state.marginals(e, labels)
            amax = max(gs.values())
            if amax < tau: continue
            labels, probs = balanced_distribution(gs)
            choice = rng.choices(labels, weights=probs, k=1)[0]
            state.add(e, choice)
            if state.size == budget: break
        tau *= x
    complete(state, buffer, budget)
    return state, passes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["email", "grqc"], default="email")
    parser.add_argument("--budgets", nargs="+", type=int, default=list(BUDGETS))
    parser.add_argument("--algorithms", nargs="+", choices=["Fair-Greedy", "Fair-Threshold", "OPFSA", "MPFSA"], default=["Fair-Greedy", "Fair-Threshold", "OPFSA", "MPFSA"])
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="root directory for result CSVs; existing files at the target are replaced",
    )
    parser.add_argument("--smoke", action="store_true", help="run only Fair-Greedy at B=9")
    args = parser.parse_args()
    if args.smoke:
        args.budgets = [9]
        args.algorithms = ["Fair-Greedy"]
    if args.dataset == "email":
        dataset, edge_file, undirected, expected_size = "Email-Eu-core", EDGE_FILE, False, (1005, 25571)
        details_path = args.output_dir / "run_details.csv"
    else:
        dataset, edge_file, undirected, expected_size = "ca-GrQc", GRQC_FILE, True, (5242, 28980)
        details_path = args.output_dir / "grqc" / "run_details.csv"
    n, edges, outgoing, indegree = load_graph(edge_file, undirected=undirected, expected_size=expected_size)
    print(f"{dataset}: n={n}, m={len(edges)}, topology={'undirected-expanded' if undirected else 'directed'}; k={K}; MC={MC}; final MC={FINAL_MC}", flush=True)
    banks = Banks(n, edges, outgoing, indegree)
    order = random.Random(SEED).sample(list(range(n)), n)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    algorithms = {"Fair-Greedy": fair_greedy, "Fair-Threshold": fair_threshold, "OPFSA": opfsa}
    access_models = {
        "Fair-Greedy": "offline",
        "Fair-Threshold": "offline",
        "OPFSA": "one-pass-fixed-order",
        "MPFSA": "replayable-fixed-order",
    }
    for B in args.budgets:
        if B < sum(LOWER) or B > sum(UPPER): raise ValueError(f"B={B} infeasible for fixed quotas")
        for name in args.algorithms:
            if name == "MPFSA":
                fn = lambda: mpfsa(banks, n, order, B, SEED + B)
            else:
                fn = lambda: algorithms[name](banks, n, order, B)
            tracemalloc.start(); t0 = time.perf_counter()
            state, passes = fn()
            elapsed = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            value, se = eval_final(banks, state.assignment)
            if state.size != B or any(not LOWER[i] <= state.counts[i] <= UPPER[i] for i in range(K)):
                raise AssertionError(f"infeasible result for {name}, B={B}")
            row = {"dataset": dataset, "n": n, "m": len(edges), "topology": "undirected-expanded" if undirected else "directed", "algorithm": name, "access_model": access_models[name], "B": B, "k": K, "lower": ";".join(map(str, LOWER)), "upper": ";".join(map(str, UPPER)), "objective": value, "evaluation_se": se, "queries": state.queries, "passes": passes, "runtime_seconds": elapsed, "peak_memory_mb": peak / (1024 * 1024), "support_size": state.size, "label_counts": ";".join(map(str, state.counts)), "decision_MC": MC, "evaluation_MC": FINAL_MC, "seed": SEED}
            rows.append(row)
            print(row, flush=True)
    if rows:
        details_path.parent.mkdir(parents=True, exist_ok=True)
        with details_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        print(f"wrote {details_path}")


if __name__ == "__main__":
    main()
