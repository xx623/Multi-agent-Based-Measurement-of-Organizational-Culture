# Preregistration draft (OSF; to be registered before any test-firm passage is processed by the final pipeline)

Status: draft. Items marked *planned* are fixed at registration. The registration link is
added to the repository README at that point.

## 1. Proposition

Separating the question of what a text reports from the question of what that report
warrants, and giving each question its own information access and its own critic,
reduces two distinct measurement errors while preserving valid evidence and warranted
scope.

## 2. Design: three budget-matched contrasts (Appendix D.2)

| Contrast | Control | Treatment | Switch |
|---|---|---|---|
| Information isolation | B: experts and Judge also receive the full masked passage | A: interpretation view only | `--no-isolation` |
| Evidence inquiry | C: critique generated but withheld; Reader re-reads with the generic self-check instruction | D: Reader answers the critique | `--no-evidence-inquiry` |
| Interpretive inquiry | E: Judge re-reads without the challenge; critic reassesses the initial claims | F: challenge passed to the Judge, reply passed to the critic | `--no-interpretive-inquiry` |

Shared outputs are generated once per passage and reused (content-addressed cache):
A–B share the whole source stage; C–D share R1 and S1; E–F share everything through C1.
Budget matching means matched call counts and generation limits per role; input lengths
differ by construction in A–B and are reported. The adjudicator prompt and model are
identical across all six arms.

Repetition: each arm is re-run three times at temperature 0 with the pinned runtime
(reproducibility under fixed decoding), and on a subset of 100 passages at temperature
0.7 with three seeds (stochastic robustness, sensitivity analysis only).

Model: pinned open-weight model (name, version, weights digest, runtime version in
`config/model_pins.json`), temperature 0, fixed seed, fixed maximum output length per
call. Second open-weight family recorded the same way.

## 3. Data

Expert reference: ~500 passages (`annotation_guidelines.md`). Paired edits: 200 pairs
from test-firm passages (`paired_edit_templates.json`). Development firms are used freely
before registration and never for reported results.

## 4. Primary outcomes

1. Agreement with the expert reference per field: category relevance (macro-F1 over
   categories and exact agreement), claim direction and structured scope (exact
   agreement on all scope fields) — `metrics.py`.
2. Correct invariance rate on irrelevant edits (both responses unchanged and equal to
   the reference).
3. Correct change rate on relevant edits (prespecified field changes in the prespecified
   direction and both responses match the reference).

## 5. Coverage, withholding safeguard and output states

Evidence completeness (share of reference conduct items present in the final record)
measures the source stage and is the main secondary outcome for C–D. Decision coverage
(share of passage-category pairs with a valid substantive decision, including a valid
none) measures the interpretation stage. For A–B the success criterion is a reduction in
false changes on promotional edits with relevant-edit sensitivity and decision coverage
each no more than five percentage points below arm B (one-sided 95 percent bound);
improvement obtained by withholding is a failure. Error rates are also compared at
matched decision coverage using relevance cut-offs applied identically to both arms.

Every passage-category pair ends valid, abstained, or invalid after the one permitted
retry; invalid responses fail the correctness endpoints, stay in their denominators and
feed a separately reported operational failure rate.

## 6. Secondary outcomes

Erroneous exclusions (reference-relevant pairs decided none or abstained), escalation
rate, run-to-run agreement, Layer 1 agreement for C–D, tokens, latency and cost per
passage and arm, re-identification probe rate.

## 7. Inference and margins (planned)

Arm differences are estimated on test firms. Uncertainty for all statistics uses paired
resampling of firms (`resampling.py`), keeping every passage, edit pair, arm and repeated
run of a firm together. Minimum margins: five F1 points for relevance agreement and five
percentage points for edit correctness. A contrast that misses its margin is reported as
a boundary result.

## 8. Comparators

Comparator 1, single-pass baseline: one prompt, raw masked passage, identical codebook,
target, admissible-evidence rules and output schema, same pinned model. Comparator 2,
faithful implementation of Li et al. (2026)'s earnings-call procedure with their released
prompts and original Miscellaneous definition, documented adaptations, reported
separately. Correlations of profiles with firm outcomes are supplementary only.

## 9. Deviations

Any change after registration is logged in the repository with date and reason.
