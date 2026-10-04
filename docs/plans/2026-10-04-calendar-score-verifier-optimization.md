# Calendar-score verifier optimization implementation plan

> For agentic workers: execute with bounded sub-agent builder and independent reviewer. User authorizes iterative exact-output optimization/testing; no routine permission stop.

**Goal:** Find the best verified low-risk configuration tested on this PC, preserving full cold-workload accounting and the unchanged12h validation-verification budget.
**Architecture:** Optimize independent cutoff proofs and SHA block construction, then make supervision wake promptly on child exit. Keep all source/resource/durability/receipt checks; no production mathematical oracle replaces the reference.
**Tech stack:** Python3.12/uv, existing NumPy/psutil, standard-library exact integers/Fraction/SHA/subprocess.
**Spec:** Reviewed sampled lifecycle Unit1 and frozen statistical protocol130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71.

## Constraints and measured evidence

- All10 full geometries/28 results/231492 bytes/1388952 words remain exact. Existing25 formal metrics,9 joints,3 sparse diagnostics,4 effect tests and88 statements are unchanged. No threshold, goal, statistical protocol, root namespace or experiment authority changes.
- Registered per-set ceiling675/1024 seconds uses twofold32768-set projection <=43200s; development verification <=43200s. Include cold cutoff/truth initialization, worker startup, independent regeneration, file checks, actual saved receipt and final pre-result resource/source checks. Retain the disclosed exclusion of benchmark accounting-record persistence/redundant checks. No cache warming or timing-boundary amendment.
- Baseline source946d5fdefd663c7d47ba36fa6448f41662bff93bf7b5b0f02982bbd40f8cd4a5 governed1.2932477s/set, child0.8196814s, eligibility=false; preserve all failed evidence.
- Primary diagnostic: cold cutoffs0.42007s; reconstruction0.29111s; totals0.01440s; cold truths0.00559s; five manifests0.06585s. Profile timing is diagnostic, not eligibility.
- Exact prototype bounds prove the three cutoff/neighbor pairs in51/8/61 terms, total~0.01785s. SHA copy/update preserves196668 compared blocks, diagnostic0.11489s versus0.15726s. Neither is a governed full workload result.
- Memory bounds remain <=8192 core calculation dates/batch, <=16MiB buffers,2GiB monitored worker/512MiB parent,20GiB reserve,600s deterministic supervisor. No source/metadata cache, unbounded prefix cache or extra dependency.

## Task1: exact bounded cutoff proof

Files: modify scripts/research/signal_calendar_score_verify.py and tests/unit/test_signal_calendar_score_verify_research.py only. Preserve generic binomial_tail exact-Fraction API.
- [ ] RED: compare new proof predicate against generic exact tails for small exhaustive n/p/cutoff/alpha cases; inclusive equality, invalid/misaligned cutoff, reflected lower tail, last-state/no remainder, below-mode fallback and invalid numeric types. Prove all three registered accepted+adjacent pairs without calling production cutoff; exercise a case geometric bound initially inconclusive.
- [ ] Implement right-tail integer recurrence. Reflect left tails via Y=n-X. Let D=d**n, T_k=comb(n,k)*a**k*(d-a)**(n-k), adjacent A=T_k*k*(d-a)/((n-k+1)*a), and partial S=sum(T_k..T_j). Exact divmod guards every recurrence. Above the mode, decreasing successive ratios give remaining mass <= T_j*(n-j)*a / ((j+1)*(d-a)-(n-j)*a). Use integer cross multiplication to prove accepted <=alpha and adjacent >alpha; never substitute partial mass for full mass. If inconclusive, continue to exact full sum; invalid cutoff raises. Equality remains inclusive for accepted and strict for adjacent.
- [ ] GREEN focused suite plus independent comparison of accepted/adjacent inequalities; record visited-term counts. Cold verification remains mandatory on every fresh benchmark child.

## Task2: exact SHA prefix reuse and prompt supervision

- [ ] RED: literal original SHA oracle compares partial-lane/peek/consume/counter-boundary behavior, forced rejection1024 and custom digest hooks. Add supervisor fake-process test proving wait timeout wakes on actual exit, timeout repeats resource samples, and final failures still kill/refuse success.
- [ ] Implement per-stream bounded hashlib prefix state; copy/update with the unchanged8-byte counter then digest. Preserve custom _digest monkeypatch/scalar fallback and immutable returned bytes; do not call the production generator. No process-global mutable prefix cache. Keep prefix changes/hash ownership safe.
- [ ] Replace unconditional supervisor sleep with process.wait(timeout=0.25); TimeoutExpired resumes polling/resource checks. Keep <=0.25 monitoring interval and every final source/resource/heartbeat/exit guard. No persistent warm worker or removed startup cost.
- [ ] Add this reviewed optimization plan to study SOURCE_PATHS; no other study implementation change. Global formatting includes Markdown Python fences; format plan before reviewer hash freeze.

## Task3: bounded iterative search, final proof and records

- [ ] Primary runs serial diagnostic comparisons across safe batch sizes2048/4096/8192 and exact cutoff/SHA combinations, all full10 in-memory deterministic paths; retain every timing/output check. Diagnostic winners do not establish eligibility. Existing original-byte baseline and all28 endpoint rows are the correctness oracle. Reject any configuration with a mismatch/failure regardless of speed.
- [ ] Stop configuration search after all three bounded sizes/combinations are compared and two consecutive independent full-set diagnostic comparisons show no >=5% improvement over the selected safe winner. Reopen only on a reproducible new bottleneck. This is the best tested configuration, not a proof of global optimality; retain all attempts, no selectively quoted fastest run. No resource/statistical amendment is part of this plan.
- [ ] Exact selected source freeze, required ordered ponytail-review then engineering/mathematical review. Related calendar/verifier/portfolio-golden/audit regression selection, strict configured mypy, whole-repo Ruff/check format. Serial foreground workload only. No commit with failing checks or unresolved review.
- [ ] Run three fresh supervised full10 cold benchmarks at the exact reviewed source, unique roots. Use the worst conservative time and retain min/median/max; all three must satisfy675/1024s/set and resource/receipt guards before declaring feasibility. If all fail, preserve blocker and profile next exact-equivalent change; iterative work stays authorized. One-set projections remain distinct from sustained phase completion/peak-memory/power-loss proof.
- [ ] Primary and reviewer independently reconstruct ALL saved raw paths/results for every final benchmark, separately verify actual source/runtime/counter/terminal/receipt/projection identities. Save exclusive digest-bound independent receipts; deterministic phase verdict remains unavailable, experimental draws0.
- [ ] For each new raw file only, dual approvals plus fixed-root/ancestor/regular identity/hash guards, durable cleanup intent, recheck/unlink/absence receipt. Keep compact indices/results/source claims/terminals/failure/approvals/timings/cleanup. Never recreate deleted counted studies or remove real/old data.
- [ ] Update build evidence, STATE/HANDOVER/TASKS and auditR3 based on actual result. Commit exact reviewed source; post-commit two bounded semantic mutants with exclusive exact-byte snapshot/finally restoration and fresh affected regressions. Documentation-only follow-up exempt from source review. Push dev per operatorD26 and verify remote equality. Preserve user-owned AGENTS.md.

## Review focus

1. A geometric remainder must bound ALL omitted mass, including the next term; cutoff neighbor and equality cannot drift.
2. Reflection must preserve inclusive lower-tail threshold and its k+1 failing neighbor.
3. Prehashed SHA must preserve frame bytes, overflow-before-consumption and rejection lane shifts; no mutable shared state.
4. Prompt process waiting must preserve final checks and failure cancellation, not merely improve clock accounting.
5. Best-tested budget must use all retained cold repetitions and worst observed time; synthetic fixtures grant no sampled/real/live authority.
