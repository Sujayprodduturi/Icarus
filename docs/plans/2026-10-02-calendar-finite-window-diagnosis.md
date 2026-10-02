# Deterministic finite-window diagnosis

Date:2026-10-02. D41 continuation after verified artificial development failure.
This is a bounded diagnostic, not a revised estimator or a new sampled version.

Build one pure typed rational-arithmetic module and deterministic tests only:

1. For a declared linear score Z_t=sum_j a_j epsilon_(t-j), with independent
   innovations of declared nonnegative variance, derive exact stationary
   autocovariances. This constructed model has a valid covariance by construction;
   it is a toy oracle, not certification of actual trading or frozen random-count laws.
   Innovations are centered, independent, with common finite nonnegative variance.
2. For fixed n and b, compute exact full-root variance Var(sum Z/sqrt(n)), each
   centered block-root variance Var((sum_block Z-(b/n)sum_full Z)/sqrt(b)), and
   adjacent centered-block covariance. Use rational quadratic/bilinear forms;
   no random sampling, Gaussian quantiles, confidence endpoints or width correction.
3. Expose the exact ratio-centering identity for finite Y,C totals: the block-minus-
   full mean equals [S_block-(C_block/C_full)S_full]/C_block where S=Y-theta C.
   Refuse zero/invalid counts. Do not substitute b/n for observed count weights.

Use bounded geometry n<=256 and filter length<=64, explicit strict validation
including bool/float refusal. Tests independently construct innovation coefficient
vectors to compare all variances/covariances, prove the iid identity1-b/n, cover
overlap/negative filter coefficients/degeneracy and test uneven-count identities.
The iid centered-root variance is sigma_squared*(1-b/n); the unscaled identity
requires unit score variance. Require exact integer1<=b<=n<=256. Adjacent starts
are i,i+1; b=n has no adjacent pair. Zero filters/variance are valid degeneracies.
Require0<C_block<=C_full and finite rational totals/theta; theta need not equal
the population target for the algebraic identity. Bound rational numerator and
denominator bit lengths as well as geometry. Test strongly unequal count weights.

The current calendar estimator, its source manifest, study evidence, frozen
criteria and sealed confirmation remain unchanged. The module produces diagnosis
only: no adopted interval, minimum-data floor, distributional coverage claim,
benchmark/real-data eligibility, trial bypass or strategy verdict.

Independent mathematics and scope review precede implementation. Then TDD,
strict static/focused regression, ordered simplicity/engineering review, commit,
bounded defect checks and exact restoration. Record which conclusions are exact
toy identities versus explanations still needing evidence for the failed laws.
