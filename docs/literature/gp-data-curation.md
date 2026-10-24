# Curating GP training data in long BO runs: a literature review

Status: research notes for the TODO.md wish-list item "Smart data curation
for long runs" (branch `bells-and-whistles`). Nothing here is implemented.
Written 2026-10-23.

## The problem

An exact GP fit on N points costs O(N³) time and O(N²) memory, and each
Badger step refits the hyperparameters (several Cholesky solves per
optimizer iteration). Roussel et al. report that maximum-likelihood fitting
takes seconds for fewer than about 300 points (PRAB 2024, Sec. III.2.2).
Typical runs here stop at 100 to 300 points within about 30 minutes, so they
never hit the wall. Hours-long runs, or a BO loop left running as slow
feedback, do: the time between steps grows until it is comparable to the
machine's drift. Kuklev et al. at the APS found that computation time
dominates past about a thousand samples, even with GPyTorch's scalable GPs.

The question: between iterations, which points can the model forget,
keeping N roughly fixed without losing what the run has learned?

The literature has two motives, and a design must decide which it serves:

1. **Cost.** Old points are correct but redundant. The model gets cheaper
   without getting worse.
2. **Staleness.** The machine drifted, so old points are wrong. Keeping them
   makes the model worse.

These usually share a mechanism but differ in which points they drop. Cost
pruning drops redundant points wherever they are. Staleness pruning drops
old points even where they are not redundant.

## Where it would plug into Xopt

Xopt already has one hook for this. `BayesianGenerator` fits its model on
`self.get_training_data(self.data)`
(`xopt/generators/bayesian/bayesian_generator.py`), while `self.data` keeps
every evaluation. Two subclasses already override it:

- TuRBO's `restrict_model_data` keeps only points inside the trust region,
  which bounds N by location.
- `TimeDependentBayesianGenerator.get_training_data`
  (`time_dependent.py`) keeps only points newer than `forgetting_time`
  seconds: a hard sliding window, by age only. The time-dependent
  generators add time as a GP input. They are not among the 8 algorithms
  Badger offers.

So any method below that selects a subset fits one override, and the
archive (Badger's run file) stays complete for free. Methods that replace
the exact GP with a sparse one plug in at the model constructor instead,
which is a bigger change.

## Families of methods

### 1. Forget by age (windows and decay)

- **Sliding window / reset.** Keep the last W points, or restart the
  dataset every so often. This is Xopt's `forgetting_time`. Bogunovic,
  Scarlett & Cevher, "Time-Varying Gaussian Process Bandit Optimization",
  AISTATS 2016 ([arXiv 1601.06650](https://arxiv.org/abs/1601.06650)),
  compare a periodic reset (R-GP-UCB) with smooth forgetting (TV-GP-UCB,
  where old points' correlation decays as (1−ε)^(Δt/2)). Smooth forgetting
  wins on both bounds and experiments. Note that TV-GP-UCB alone does not
  shrink N: it down-weights old points but still carries them.
- **Weighted GP.** Deng et al., "Weighted Gaussian Process Bandits for
  Non-stationary Environments", AISTATS 2022
  ([arXiv 2107.02371](https://arxiv.org/abs/2107.02371)) (WGP-UCB),
  weights old observations down in the regression. Same caveat: it bounds
  the influence of old points, not the cost.
- **Kernel RLS tracker.** Van Vaerenbergh, Lázaro-Gredilla & Santamaría,
  "Kernel Recursive Least-Squares Tracker for Time-Varying Regression",
  IEEE TNNLS 23(8), 2012. This is a GP regressor with a fixed memory of M
  basis points, O(M²) per update. It combines forgetting ("back to the
  prior", which pulls the posterior towards the prior) with principled
  pruning of the least useful basis point. It is the closest classical
  match to "fixed budget, older first, keep the informative". Python
  implementation: PyKRLST.

Verdict: cheap, simple, and already half-built in Xopt. It is blind to
informativeness, though: it drops the one good point near the optimum as
readily as a redundant one.

### 2. Remove stale points by relevance (the current front)

- **W-DBO.** Bardou, Thiran & Ranieri, "This Too Shall Pass: Removing
  Stale Observations in Dynamic Bayesian Optimization", NeurIPS 2024
  ([arXiv 2405.14540](https://arxiv.org/abs/2405.14540), code:
  [WDBO-ALGORITHM/wdbo_algo](https://github.com/WDBO-ALGORITHM/wdbo_algo)).
  - A point's relevance is the Wasserstein-2 distance between the GP
    posterior with and without it, integrated over the domain and all
    future times. A closed-form approximation makes this cheap, but it
    assumes a kernel separable into space × time.
  - A point is removed when its relevance falls under a budget that grows
    as b(t) = (1+α)^t; α = 1/4 was robust across benchmarks.
  - Datasets stay tiny (about 15 points at peak on Ackley, settling to
    about 7). W-DBO beat TV-GP-UCB, R-GP-UCB, ABO and plain GP-UCB on 10 of
    12 benchmarks.
- **BOLT.** Bardou & Thiran, "Time-Varying Bayesian Optimization Without a
  Metronome" (2025, [arXiv 2501.18963](https://arxiv.org/abs/2501.18963);
  also published as "Optimizing Through Change: Bounds and Recommendations
  for TVBO Algorithms"). This is the paper most directly about our
  question. It bounds regret in terms of the response time R(n), which
  grows with dataset size n, and gives two recommendations:
  1. *Dataset size:* keep n* = argmax_n Σ_{i=1..n} k_T²(i·R(n)), where k_T
     is the learned temporal kernel. This trades information against
     sampling rate.
  2. *Which point to drop:* the one whose removal changes the posterior
     least (minimum W₂, as in W-DBO). Their Theorem 3.8 justifies doing
     this greedily, one point at a time.

  BOLT measures R(n) online by fitting a cubic to (|D|, wall-clock time)
  pairs. It needs no budget hyperparameter, and it matched or beat
  W-DBO, ABO, ET-GP-UCB, TV-GP-UCB, R-GP-UCB and a sliding window on 10
  benchmarks. Built on BoTorch.
- **ET-GP-UCB.** Brunzema, von Rohr, Solowjow & Trimpe, "Event-Triggered
  Time-Varying Bayesian Optimization", TMLR 2025
  ([arXiv 2208.10790](https://arxiv.org/abs/2208.10790)). The dataset is
  reset only when a new measurement is inconsistent with the GP's uniform
  error bound, i.e. when drift is actually detected. This is a useful
  trigger even if the response is softer than a full reset.
- **APS adaptive BO.** Kuklev, Borland, Fystro, Shang & Sun, "Online
  Accelerator Tuning with Adaptive Bayesian Optimization", NAPAC2022,
  paper THXD4, and "Time-aware Bayesian optimization for adaptive particle
  accelerator tuning", NeurIPS ML4PS workshop 2022. This is the
  accelerator-specific precedent.
  - The model is a Matérn ARD kernel times a spectral-mixture kernel in
    time.
  - Instead of a cutoff or random subsampling, they use "time-based
    importance bandwidth subsampling". It discards old data "that does not
    contribute to the overall model outside some specific time scale",
    ranked by impact on the current fit. Points in slowly varying
    dimensions go first, and data older than one full period of a periodic
    signal may be thinned.
  - Signals faster than the upper bandwidth cutoff (typically 0.05 Hz, a
    20 s period) are averaged.
  - In the experiment, 15 minutes of history was subsampled to 100 points.
    The code (APSopt/pysddsoptimize) is internal to Argonne. The ML4PS
    paper names O(n³) as the limitation that keeps problems under about 20
    parameters.

Verdict: this is the principled answer to "keep the most informative,
older first". The ranking criterion (how much the posterior moves without
the point) does the right thing in both regimes: a redundant point moves
nothing, and a decorrelated old point moves nothing about the future. The
catch is that the cheap closed forms need time as a kernel input.

### 3. Budgeted informative subsets (no time model needed)

- **Sparse online GP.** Csató & Opper, "Sparse On-Line Gaussian
  Processes", Neural Computation 14(3):641–668, 2002. The model keeps at
  most m basis vectors. A new point is added only if it is novel (its
  projection residual onto the current basis exceeds a threshold). When
  the budget is exceeded, the basis vector whose removal costs least (a
  KL-based score) is deleted and its information projected onto the rest.
- **Informative Vector Machine.** Lawrence, Seeger & Herbrich, "Fast
  Sparse Gaussian Process Methods: The Informative Vector Machine", NIPS
  2002 ([PDF](https://herbrich.me/papers/ivm.pdf)). This is greedy forward
  selection of an active set by differential entropy, which favours points
  that most reduce posterior variance. The entropy objective is
  submodular, so greedy selection is within (1−1/e) of the best subset of
  that size.
- **Leverage / posterior-variance criteria in general.** These are the same
  idea as the two above, for a static function. Without a time term they
  never drop a point for being old, only for being redundant.

Verdict: this matches the cost motive exactly and needs no change to the
kernel. It is the simplest "smart" option for Badger's existing
algorithms (expected improvement, UCB, etc. on a static function), where
staleness is not modelled anyway.

### 4. Prune by region

- **ZoMBI memory pruning.** Siemenn & Buonassisi, "Decreasing the
  Computing Time of Bayesian Optimization using Generalizable Memory
  Pruning", IEEE HPEC 2023
  ([arXiv 2309.04510](https://arxiv.org/abs/2309.04510); ZoMBI itself:
  [arXiv 2208.13771](https://arxiv.org/abs/2208.13771)).
  - Every N = 20 experiments, take the m best points, shrink each
    dimension's bounds to their min/max, and forget everything outside.
  - Compute time becomes a sawtooth instead of a polynomial: up to 100×
    faster with no loss of convergence on 6-D Ackley over 1000
    experiments, with GP or neural-network surrogates.
  - It is aggressive, though: it assumes a single basin and cannot widen
    the bounds again.
- **TuRBO.** Trust-region BO fits the GP only inside the trust region (in
  Xopt: `restrict_model_data`). Badger already offers it, so it is a
  zero-work baseline for "region-bounded N".
- **FocalBO.** Wei, Zhuang, Soedarmadji & Sui, "Scalable Bayesian
  Optimization via Focalized Sparse Gaussian Processes", 2024
  ([arXiv 2412.20375](https://arxiv.org/abs/2412.20375), code:
  [yunyuewei/FocalBO](https://github.com/yunyuewei/FocalBO)). This is a
  soft version. Training points are weighted by their kernel similarity to
  the current search region, and the region zooms hierarchically. It uses
  a sparse GP with 50 to 200 inducing points and handles thousands of
  evaluations.

Verdict: this is effective when the run has converged on one region. It is
risky with drift, which can move the optimum back out of the region.

### 5. Keep all the data, use a sparse model

Rather than drop points, these approximate the GP with M ≪ N inducing
points, at O(NM²) cost.

- Titsias, "Variational Learning of Inducing Variables in Sparse Gaussian
  Processes", AISTATS 2009. Hensman, Fusi & Lawrence, "Gaussian Processes
  for Big Data" (SVGP), UAI 2013.
- **Streaming sparse GPs.** Bui, Nguyen & Turner, "Streaming Sparse
  Gaussian Process Approximations", NIPS 2017
  ([code](https://github.com/thangbui/streaming_sparse_gp)). These update
  the posterior from new data without revisiting old data.
- **Online variational conditioning.** Maddox, Stanton & Wilson,
  "Conditioning Sparse Variational Gaussian Processes for Online
  Decision-making", NeurIPS 2021
  ([code](https://github.com/wjmaddox/online_vargp)). This gives BoTorch's
  `condition_on_observations` for SVGPs, i.e. fantasies and look-ahead
  acquisition functions with sparse models.
- **Where to put inducing points for BO.** Moss, Ober & Picheny, "Inducing
  Point Allocation for Sparse Gaussian Processes in High-Throughput
  Bayesian Optimisation", AISTATS 2023
  ([arXiv 2301.10123](https://arxiv.org/abs/2301.10123)). Standard
  allocation spreads inducing points evenly, wasting them away from the
  optimum. Their quality-diversity DPP (L = q·K·q, with q an improvement
  score) concentrates them where the optimizer cares. Implemented in
  Trieste.
- **Accelerator precedent.** McIntire, Ratner (SLAC) & Ermon, "Sparse
  Gaussian Processes for Bayesian Optimization", UAI 2016. This is an
  online sparse GP whose updates favour high-performing regions, applied
  to tuning the LCLS FEL. (Read from the abstract; the PDF was
  unreachable.)

Verdict: this is the right tool at thousands to millions of points. At our
scale (hundreds to a few thousand points) it adds a variational training
loop, its own hyperparameters and a model swap inside Xopt, for a problem
that pruning solves with an override.

### 6. Just compute faster

- **Exact GPs on GPUs.** Gardner et al., "GPyTorch: Blackbox Matrix-Matrix
  Gaussian Process Inference with GPU Acceleration", NeurIPS 2018
  ([arXiv 1809.11165](https://arxiv.org/abs/1809.11165)), and Wang et al.,
  "Exact Gaussian Processes on a Million Data Points", NeurIPS 2019
  ([arXiv 1903.08114](https://arxiv.org/abs/1903.08114)). Conjugate
  gradients plus GPU matrix multiplies replace the Cholesky. They trained
  on 10⁶ points in under 2 h on multiple GPUs, with predictions in under
  1 s after caching.
- **LOVE.** Pleiss et al., "Constant-Time Predictive Distributions for
  Gaussian Processes", ICML 2018. This makes posterior variances fast,
  which matters for acquisition optimization.

Verdict: these are already in the stack (Xopt uses BoTorch/GPyTorch).
Below a few thousand points on a control-room CPU, the dense Cholesky is
still fastest. Fitting hyperparameters less often, e.g. only every k steps,
is a free constant-factor gain that stacks with any of the above.

## How this maps onto our situation

| Our situation | Fits best | Why |
|---|---|---|
| Static objective, long run, slow fits (Badger's 8 algorithms) | Family 3: greedy budget (posterior-variance / W₂ leave-one-out score), in a `get_training_data` override | Cost motive only; no kernel change; archive intact |
| Drifting machine, time-aware GP | Family 2: BOLT or W-DBO style removal, on Xopt's time-dependent generators | Handles redundancy and staleness with one score; BOLT also picks the budget |
| Drift you only want to detect | ET-GP-UCB trigger, then a window or prune | Cheap test; no time kernel needed |
| Converged into one basin | TuRBO, already in Badger | Zero work |
| 10⁴+ points | Family 5 or 6 | Pruning loses too much at that ratio |

## A suggested prototype

The smallest experiment that would tell us whether this is worth more:

1. A `get_training_data` override on an Xopt Bayesian generator, with a
   `max_training_points` budget (default off). When N exceeds the budget,
   greedily drop the point with the smallest leave-one-out effect on the
   posterior mean and variance over the current candidate region. Break
   ties by age, oldest first.
   - With a static kernel, this is family 3.
   - On `TimeDependentBayesianGenerator`, the same score becomes W-DBO's.
   - Always keep the incumbent best feasible point and points near
     constraint boundaries. Removing those changes the decisions, not just
     the fit.

   Exact leave-one-out quantities come cheaply from one Cholesky of the
   full set (the standard closed-form LOO identities), so scoring all N
   points costs about one fit.
2. Benchmark offline against the VirtualAccelerator sim. Use the
   `99_Sim_VirtualAccelerator_MADXSuite` environment and a 1000+ step run,
   with and without slow drift injected into a lattice parameter. Compare
   wall-clock time per step and best-found value against the hard window
   (`forgetting_time`) and no pruning.
3. Only if that pays off: expose the budget as a generator parameter in
   Badger (pydantic field, so it shows in the Parameters panel). Consider
   upstreaming it to Xopt, since nothing here is Badger-specific, which is
   what the wish-list entry anticipated.

## Open questions

- **What "informative" means for us.** Is it near the optimum (FocalBO,
  IMP-DPP), spread out (IVM, DPP diversity), or near constraint
  boundaries? Constraint models are separate GPs in Xopt. A point
  redundant for the objective may matter for a constraint, so the score
  should take the maximum across all models' GPs.
- **Hyperparameter fit vs. posterior.** One could fit hyperparameters on a
  small diverse subset (e.g. farthest-point sampling, as suggested in the
  tutorial [arXiv 2603.10992](https://arxiv.org/abs/2603.10992), not yet
  read) and condition on more points. That would split the two costs.
- **Is cost actually the bottleneck in our runs?** Measure the per-step fit
  time vs. N on the operator machine before building anything. If runs
  never pass about 500 points, this stays on the wish list.
- **Interaction with the other wish-list items.** Seeding a run with
  historical data and widening a variable's range mid-run both grow N up
  front. A budget would make seeding with large archives practical.

## Also found, not yet read

- "Frugal Bayesian Optimization",
  [arXiv 2607.29225](https://arxiv.org/abs/2607.29225) (2026).
- Nyikosa, Osborne & Roberts, "Bayesian Optimization for Dynamic Problems",
  [arXiv 1803.03432](https://arxiv.org/abs/1803.03432) (2018).
- "Lifelong Bayesian Optimization",
  [arXiv 1905.12280](https://arxiv.org/abs/1905.12280).
- [arXiv 2509.05658](https://arxiv.org/abs/2509.05658), which states that
  sliding-window TVBO is used through Xopt for drift correction. This is
  worth reading for how others drive `forgetting_time` in practice.
- Roussel et al., "Bayesian optimization algorithms for accelerator
  physics", PRAB 27, 084801 (2024)
  ([arXiv 2312.05667](https://arxiv.org/abs/2312.05667)). This was read for
  context: Sec. III.2.4 covers O(n³) scaling, and Sec. III.3.4 covers
  adaptive BO at the APS linac and the KARA storage ring.

Reading depth: the APS NAPAC/ML4PS papers and the memory-pruning paper
were read in full. W-DBO and BOLT were read from their arXiv HTML. The
rest are from abstracts and summaries, and should be checked before relying
on specific numbers.
