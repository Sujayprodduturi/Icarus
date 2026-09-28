# Step 6a.2 completion authority proposal

**Status: PROPOSED — requires an operator decision. It is not approved and enables nothing today.**

## Plain-English recommendation

A completion seal file cannot, by itself, truthfully prove that the whole two-hour operation finished.
The current contract requires the deadline to cover the seal write, file sync, directory sync, close, and
final deadline/resource checks. Seal bytes must be chosen before those later operations occur. Two runs
can therefore leave identical surviving bytes even though one finishes before the deadline and the other
fails after it. More hashes or sidecars cannot record a fact that did not exist when their bytes were fixed.

Treat persisted seal bytes as an inert **candidate record**. Issue a privately issued, identity-bound,
process-local completion capability only after the file is written, file-synced, directory-synced, and closed once,
and the original deadline and resource boundary have passed their final checks. The capability dies with
the process and is the only completion authority.

Validation would require both the same-process capability and a fresh, full verification of the exact
calibration claim, result, and candidate-seal bytes. Calibration must be PASSED with its non-null first
passing floor. Intact files after process loss remain evidence for review, but cannot authorize validation.
There is no resume, redraw, overwrite, truncation, deletion, or cleanup path.

A future combined calibrate-then-validate invocation must be separately specified, reviewed, and approved.
This proposal does not implement or authorize that invocation.

## Contract clauses that would require explicit amendment

1. **Section 6, seal authority.** Replace the statement that a persisted completion seal proves
   verification verdict COMPLETE with two stages: inert candidate bytes, then a process-local
   completion capability issued only after every durability operation and final original-boundary check.
2. **Section 6, exact schema.** Revise the seal schema only after the operator chooses this authority model.
   The revision must distinguish a pre-write measurement snapshot from completed authority; the current
   exact schema must not be silently reinterpreted.
3. **Section 7, validation evidence.** Require the live completion capability plus fresh full verification
   of the exact calibration trio. A user path remains only a locator. Persisted files alone never unlock
   validation, even when every hash and statistic verifies.
4. **Section 8, deadline.** Keep the original monotonic two-hour deadline active through candidate write,
   file sync, directory sync, the single close attempt, and final deadline/resource checks. Capability
   issuance occurs only after those checks succeed.
5. **Section 8, failures.** Any write, sync, close, identity, deadline, or resource failure leaves no
   capability. Existing no-cleanup and stable-claim rules continue to make that attempt non-resumable.

The candidate record may contain measurements captured before its bytes are written. Those fields describe
a pre-write verification snapshot only. They cannot claim that later sync, close, or final checks succeeded.
The exact revised field names, states, canonical encoding, and capability binding remain design work under
the operator-approved choice.

## Crash and failure truth table

| Event | Persisted candidate possible? | Completion capability? | Validation allowed? |
|---|---:|---:|---:|
| Failure before candidate creation | No | No | No |
| Partial/short candidate write | Partial bytes | No | No |
| Candidate file fsync failure | Possibly | No | No |
| Candidate directory fsync failure | Possibly | No | No |
| Candidate close reports failure | Possibly | No | No |
| Final deadline/resource/identity check fails | Yes | No | No |
| Process crashes after candidate syncs succeed, before capability | Yes | No | No |
| Capability issued, then process exits before validation | Yes | Lost | No |
| Same process holds capability; fresh trio verification fails | Yes | Yes | No |
| Same process holds capability; fresh trio verifies PASSED and first floor | Yes | Yes | Eligible only for the future reviewed combined invocation |

## Required acceptance tests for a future implementation

- Candidate bytes alone, including copied or perfectly reverified bytes, cannot construct authority.
- Issue capability only after file sync, directory sync, one close attempt, and final boundary checks.
- Deadline, resource, identity, write, sync, or close failure prevents capability issuance.
- Close-after-release is never retried against a reused descriptor.
- Crash injection at every durability boundary leaves no recoverable authorization.
- Restart with an intact trio refuses before any validation claim or RNG access.
- Fresh verification detects changed size, identity, bytes, claim, result, verdict, or selected floor.
- Same-process validation requires the exact capability-bound trio, PASSED, and the first non-null floor.
- Failure never deletes, repairs, truncates, overwrites, resumes, redraws, or changes statistical inputs.

## Disadvantages and rejected shortcut

This model sacrifices automatic validation after a crash, even after valid calibration. The stable claim
keeps that attempt single-use; another attempt needs a separately reviewed new-attempt path under existing
policy. A deterministic conceptual model, not a filesystem or RNG experiment, produced the same candidate hash
66e0cf36c423471da27e0f236f8daa11873542930a1369b425244cb2bdcec461 for success at 7,199.5 seconds,
deadline failure at 7,200.5 seconds, and fsync failure at 7,199.5 seconds; only success had live authority.

Persisted-only recovery requires changing the historical deadline/durability contract or authorizing recovery semantics.
Under the same final write/sync/close/deadline requirement, more sidecars cannot solve the ordering contradiction.
No threshold, safety invariant, single-attempt rule, or disabled-inference boundary is changed or waived.
