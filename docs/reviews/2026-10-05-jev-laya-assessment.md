# Jev and Laya assessment for Icarus

As of2026-10-05. Operator asked whether these recently released choice/probability models enhance Icarus. Root researched primary documentation and independently checked the focused research agent's findings. No model installation, download, paid API call or integration was performed.

**Recommendation:** optional candidates for later text classification; unnecessary for the current exact uncertainty calculation, experiment-control and verifier work. This is an architecture assessment, not an Icarus accuracy or trading-performance measurement.

[Jev's official introduction](https://docs.typesafe.ai/introduction) describes structured choice, rubric-score and yes/no questions. Its [confidence definition](https://docs.typesafe.ai/confidence) is computed from the returned option distribution. It is neither an independent statistical confidence interval nor evidence of a trading advantage.

[Jev's own limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13), reviewed by the vendor2026-10-02 for jev-1.13, warn about arithmetic, counting, date comparison, adversarial inputs and option-order effects. Exact accounting, dates, risk limits and experiment gates belong in deterministic code.

[Laya's publisher model card](https://huggingface.co/convaiinnovations/laya) describes Apache-2.0 open weights, local deployment and multilingual checkpoints. It also documents shipped overconfidence, weak base-checkpoint performance on its typed-decision benchmark, and the need for domain-specific evaluation/calibration. Those published tests do not establish performance on Indian financial news.

PRD section10 gives News/Sentiment a relevance/sentiment-scoring role and Macro a context role. Either model might later help classify announcements or route uncertain text for deeper analysis. A headline-label probability is not a calibrated probability of a profitable trade. Typed output reduces some format failures; a valid label can still be wrong.

Before adoption, compare a pinned candidate against simple rules and the planned Haiku scorer on point-in-time Indian financial text. Use separate calibration and held-out evaluation, measure class errors and probability accuracy as well as latency/cost/resource use, and account for uncertain or missing answers. This proposal is not an evaluation authorization or approved threshold change.

Keep outputs as research data, with no broker access or ability to approve experiments, promote strategies, alter hard limits or originate orders. Local model workloads must not preempt execution. Finish the current milestone first; revisit only when a defined text-processing need warrants measurement.
