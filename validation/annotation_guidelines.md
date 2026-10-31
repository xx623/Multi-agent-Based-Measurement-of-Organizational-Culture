# Annotation guidelines and expert reference labels (Technical Appendix D.4)

Status: draft protocol for Stage 2; to be calibrated, frozen and preregistered before any
test-firm passage is coded. Controlled vocabularies: `controlled_vocabularies.json`.

## Sampling

About 500 passages: 400 from at least 40 held-out test firms and 100 from at least 10
development firms, sampled before any screening and stratified by evidence type
(completed action, ongoing practice, plan, declaration only, mixed), with about ten
passages per firm and at least 40 per expected category.

## Annotators and procedure

Coders with graduate training in management or finance research, paid at the
institution's standard research-assistant rate. They never see model outputs.

1. Calibration on a separate sample of 50 development-firm passages; instructions are
   refined during calibration only.
2. The codebook and instructions are frozen and preregistered, together with any decision
   to exclude a field from the primary outcomes on reliability grounds (calibration
   evidence only).
3. Every validation passage is coded independently by two annotators.
4. Disagreements are adjudicated by a third senior coder.
5. The adjudicated labels are the expert reference.

Krippendorff's alpha is reported per field and per category on the independent codes
before adjudication; it guides training and is not treated as proof of validity. The
central fields (relevance, direction, structured scope) are never dropped after seeing
test data; if calibration shows one cannot be coded reliably, that limits the conclusions
drawn for it and is stated as such.

## Layer 1: source

For each reported conduct item in the passage: supported by the passage; qualifiers
omitted; conduct items missing; timing, status, content type, scope fields and direction
correct; and, for each gap, whether the passage states the information (absent, unclear,
present). Items are written in the Reader's format (actor, conduct, timing, status,
content_type, direction, origin, scope type/target/extent, qualifications, verbatim
excerpt of at most 25 words with sentence ID).

## Layer 2: interpretation

Coded, where possible, by a different person from the Layer 1 record only. For each
category: relevance (none, weak, moderate, strong); for each claim: normative direction,
origin, structured scope (type on the controlled vocabulary; target as a short string
normalized to the placeholder or unit name; extent as one, some, all, named or
unspecified), conduct status, and content type (expectation, rule, routine, episode).
Scope is scored field by field, so equivalent prose descriptions cannot be penalized.

Coding rules (from `codebook.json`): routine only when the passage describes the
conduct as standard practice for a defined set of actors; an episode on its own supports
at most weak relevance; plans and declarations never establish implemented practice;
outcomes are not conduct expectations; an externally imposed requirement is still
reported normative content with origin external; absence of evidence is insufficiency,
not opposition.

## Ethics

Annotators read masked executive statements about firms; no individual employee is
identified. Ethics approval from the institution's research ethics committee is obtained
before annotation begins (reference withheld for anonymous review); informed consent
covers the use of coding decisions in published reliability statistics.
