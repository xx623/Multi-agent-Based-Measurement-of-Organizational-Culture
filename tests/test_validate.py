"""Cross-field validation rules of Technical Appendix B, checked offline."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import validate as V  # noqa: E402
from pipeline.schemas import category_names, load_codebook  # noqa: E402

CB = load_codebook(ROOT)
VOC = CB["vocabularies"]
CATS = category_names(CB)
INNOV = "Innovation and adaptability"
WINDOW = {"units": [
    {"sid": "S1", "speaker_role": "executive", "window_role": "focus", "text": "We champion innovation."},
    {"sid": "S2", "speaker_role": "executive", "window_role": "focus",
     "text": "We stopped twelve pilots this year; teams must share unsuccessful results at monthly reviews."}]}


def item(**over):
    base = {"id": "E1", "actor": "company", "conduct": "stopped twelve pilots", "timing": "this year",
            "status": "completed", "content_type": "episode", "direction": "unclear", "origin": "unstated",
            "scope": {"type": "unspecified", "target": "Not stated", "extent": "unspecified"}, "qualifications": [],
            "excerpt": "We stopped twelve pilots this year", "excerpt_sentence": "S2"}
    base.update(over)
    return base


E2 = item(id="E2", actor="teams", conduct="share unsuccessful results at monthly reviews", status="ongoing",
          content_type="routine", direction="required", origin="internal",
          scope={"type": "team or role", "target": "teams", "extent": "all"},
          qualifications=["compliance not reported"], excerpt="teams must share unsuccessful results at monthly reviews")


def record(items, flags=None, responses=None, removed=None):
    return {"passage_id": "P", "items": items,
            "declarations": [{"id": "D1", "text": "We champion innovation.", "sentence": "S1"}],
            "unresolved_flags": flags or [], "flag_responses": responses or [], "removed_item_ids": removed or []}


def strip(it):
    return {k: v for k, v in it.items() if k not in ("excerpt_sentence", "excerpt_span")}


VIEW = {"passage_id": "P", "items": [strip(item()), strip(E2)], "unresolved": [], "completeness_uncertain": False}
CRITIQUE = {"passage_id": "P", "flags": [
    {"id": "F1", "type": "MISSING_ITEM", "target_item": "none", "sentences": ["S2"], "question": "Is the review rule conduct?"},
    {"id": "F2", "type": "SCOPE_OR_STATUS_ERROR", "target_item": "E1", "sentences": ["S2"], "question": "Which units?"}],
    "complete_and_supported": False}


def claim(**over):
    base = {"id": "K1", "category": INNOV, "status": "supported", "evidence_ids": ["E2"],
            "conduct": "teams share unsuccessful results at monthly reviews", "content_type": "routine",
            "direction": "required", "origin": "internal",
            "scope": {"type": "team or role", "target": "teams", "extent": "all"}, "conduct_status": "ongoing",
            "generalized_from_event": False}
    base.update(over)
    return base


def judgment(claims, round_no=1, responses=None):
    return {"passage_id": "P", "round": round_no, "claims": claims, "completeness_uncertain_affects": [],
            "strongest_objection": "which teams is not stated", "objection_responses": responses or []}


def critique_c(round_no, objections, accepted, resolved=None):
    return {"passage_id": "P", "round": round_no, "objections": objections, "accepted_claims": accepted,
            "resolved_objection_ids": resolved or []}


def adjudication(kept=True, escalate=False, limitation_kind="SOURCE_INHERENT", action="narrow"):
    cats = {c: {"relevance": "none", "direction": "none", "claims": []} for c in CATS}
    if kept:
        cats[INNOV] = {"relevance": "strong", "direction": "required", "claims": [{
            "claim_ref": "K1", "relevance": "strong", "conduct": "teams share unsuccessful results at monthly reviews",
            "content_type": "routine", "direction": "required", "origin": "internal",
            "scope": {"type": "team or role", "target": "teams", "extent": "all"}, "conduct_status": "ongoing",
            "evidence_for": ["E2"], "evidence_against": [],
            "limitations": [{"text": "compliance unobserved", "kind": limitation_kind}]}]}
    return {"passage_id": "P", "measurement": {"passage_id": "P", "categories": cats},
            "process": {"passage_id": "P", "actions": [{"claim_ref": "K1", "action": action}],
                        "unresolved_objections": [], "escalate_to_human": escalate, "output_state": "valid"}}


class ReaderRules(unittest.TestCase):
    def test_valid_initial_record(self):
        errors, _ = V.validate_record(record([item()]), passage_id="P", phase="initial", window=WINDOW, vocab=VOC)
        self.assertEqual(errors, [])

    def test_excerpt_must_be_verbatim_and_short(self):
        errors, _ = V.validate_record(record([item(excerpt="We stopped twelve pilot projects")]), passage_id="P",
                                      phase="initial", window=WINDOW, vocab=VOC)
        self.assertTrue(any("not verbatim" in e for e in errors))
        long = item(excerpt=" ".join(["word"] * 26))
        errors, _ = V.validate_record(record([long]), passage_id="P", phase="initial", window=WINDOW, vocab=VOC)
        self.assertTrue(any("limit is 25" in e for e in errors))

    def test_initial_phase_has_no_flags(self):
        rec = record([item()], flags=[{"flag_id": "F1", "type": "MISSING_ITEM", "target_item": "none",
                                      "source_states": "absent", "note": "x"}])
        errors, _ = V.validate_record(rec, passage_id="P", phase="initial", window=WINDOW, vocab=VOC)
        self.assertTrue(any("initial phase" in e for e in errors))

    def test_revision_answers_every_flag_and_carries_unresolved(self):
        responses = [{"flag_id": "F1", "action": "added_item", "source_states": "present", "reason": "S2 states it"}]
        rec = record([item(scope={"type": "unspecified", "target": "Not stated", "extent": "unspecified"}), E2],
                     responses=responses)
        errors, _ = V.validate_record(rec, passage_id="P", phase="revision", window=WINDOW, vocab=VOC,
                                      previous=record([item()]), critique=CRITIQUE)
        self.assertTrue(any("without a flag_response" in e and "F2" in e for e in errors))
        responses.append({"flag_id": "F2", "action": "amended", "source_states": "absent", "reason": "S2 silent"})
        errors, _ = V.validate_record(rec, passage_id="P", phase="revision", window=WINDOW, vocab=VOC,
                                      previous=record([item()]), critique=CRITIQUE)
        self.assertTrue(any("not carried in unresolved_flags" in e for e in errors))
        rec["unresolved_flags"] = [{"flag_id": "F2", "type": "SCOPE_OR_STATUS_ERROR", "target_item": "E1",
                                    "source_states": "absent", "note": "which units is not stated"}]
        errors, _ = V.validate_record(rec, passage_id="P", phase="revision", window=WINDOW, vocab=VOC,
                                      previous=record([item()]), critique=CRITIQUE)
        self.assertEqual(errors, [])

    def test_dropped_items_must_be_listed(self):
        rec = record([E2])
        errors, _ = V.validate_record(rec, passage_id="P", phase="revision", window=WINDOW, vocab=VOC,
                                      previous=record([item()]), critique={"passage_id": "P", "flags": [],
                                                                            "complete_and_supported": True})
        self.assertTrue(any("dropped without listing" in e for e in errors))


class SkepticRules(unittest.TestCase):
    def test_missing_item_targets_none_and_flag_consistency(self):
        bad = copy.deepcopy(CRITIQUE)
        bad["flags"][0]["target_item"] = "E1"
        errors, _ = V.validate_critique(bad, passage_id="P", window=WINDOW, record=record([item()]), vocab=VOC)
        self.assertTrue(any("MISSING_ITEM must have target_item 'none'" in e for e in errors))
        ok = copy.deepcopy(CRITIQUE)
        ok["complete_and_supported"] = True
        errors, _ = V.validate_critique(ok, passage_id="P", window=WINDOW, record=record([item()]), vocab=VOC)
        self.assertTrue(any("exactly when flags is empty" in e for e in errors))


class JudgeRules(unittest.TestCase):
    def test_valid_claim(self):
        errors, _ = V.validate_judgment(judgment([claim()]), passage_id="P", round_no=1, view=VIEW,
                                        categories=CATS, vocab=VOC)
        self.assertEqual(errors, [])

    def test_scope_cannot_be_widened(self):
        wide = claim(scope={"type": "organization-wide", "target": "company", "extent": "all"})
        errors, _ = V.validate_judgment(judgment([wide]), passage_id="P", round_no=1, view=VIEW,
                                        categories=CATS, vocab=VOC)
        self.assertTrue(any("wider" in e for e in errors))

    def test_episode_only_claims_must_declare_generalization(self):
        ep = claim(evidence_ids=["E1"], content_type="episode", direction="unclear", origin="unstated",
                   scope={"type": "unspecified", "target": "Not stated", "extent": "unspecified"},
                   conduct_status="completed")
        errors, _ = V.validate_judgment(judgment([ep]), passage_id="P", round_no=1, view=VIEW, categories=CATS,
                                        vocab=VOC)
        self.assertTrue(any("rule 3" in e for e in errors))

    def test_round_two_answers_every_objection(self):
        c1 = critique_c(1, [{"id": "O1", "claim_ref": "K1", "criterion": "e", "evidence_ids": ["E2"],
                              "reason": "scope", "narrowest_claim": "teams under the rule"}], [])
        errors, _ = V.validate_judgment(judgment([claim()], 2), passage_id="P", round_no=2, view=VIEW,
                                        categories=CATS, vocab=VOC, critique=c1)
        self.assertTrue(any("without a response" in e for e in errors))


class CriticRules(unittest.TestCase):
    def test_every_supported_claim_is_covered(self):
        j = judgment([claim(), claim(id="K2", category="Other reported norms")])
        c = critique_c(1, [], [{"claim_ref": "K1", "reason": "fine"}])
        errors, _ = V.validate_interpretive_critique(c, passage_id="P", round_no=1, judgment=j, view=VIEW, vocab=VOC)
        self.assertTrue(any("neither objected to nor accepted" in e and "K2" in e for e in errors))

    def test_round_one_cannot_resolve(self):
        c = critique_c(1, [], [{"claim_ref": "K1", "reason": "fine"}], resolved=["O1"])
        errors, _ = V.validate_interpretive_critique(c, passage_id="P", round_no=1, judgment=judgment([claim()]),
                                                     view=VIEW, vocab=VOC)
        self.assertTrue(any("empty in round 1" in e for e in errors))


class AdjudicatorRules(unittest.TestCase):
    J2 = judgment([claim()], 2)
    C1 = critique_c(1, [{"id": "O1", "claim_ref": "K1", "criterion": "e", "evidence_ids": ["E2"], "reason": "scope",
                         "narrowest_claim": "teams under the rule"}], [])
    C2 = critique_c(2, [], [{"claim_ref": "K1", "reason": "narrowed"}], resolved=["O1"])

    def check(self, adj):
        return V.validate_adjudication(adj, passage_id="P", view=VIEW, judgment2=self.J2, critique1=self.C1,
                                       critique2=self.C2, categories=CATS, vocab=VOC)[0]

    def test_valid(self):
        self.assertEqual(self.check(adjudication()), [])

    def test_all_categories_required(self):
        adj = adjudication()
        del adj["measurement"]["categories"]["Customer-oriented"]
        self.assertTrue(any("missing" in e for e in self.check(adj)))

    def test_category_relevance_equals_max_claim(self):
        adj = adjudication()
        adj["measurement"]["categories"][INNOV]["relevance"] = "weak"
        self.assertTrue(any("maximum claim relevance" in e for e in self.check(adj)))

    def test_escalation_required_for_resolvable_limitations(self):
        adj = adjudication(limitation_kind="RESOLVABLE", escalate=False)
        self.assertTrue(any("escalate_to_human must be true" in e for e in self.check(adj)))
        self.assertEqual(self.check(adjudication(limitation_kind="RESOLVABLE", escalate=True)), [])

    def test_withheld_claim_cannot_remain_in_measurement(self):
        adj = adjudication(kept=True, action="withhold")
        self.assertTrue(any("still listed in measurement" in e for e in self.check(adj)))

    def test_abstention_lists_no_claims(self):
        adj = adjudication()
        adj["process"]["output_state"] = "abstained"
        adj["process"]["abstention_reason"] = "limitation remains"
        self.assertTrue(any("an abstention decides no category" in e for e in self.check(adj)))

    def test_scope_not_wider_than_judge_claim(self):
        adj = adjudication()
        adj["measurement"]["categories"][INNOV]["claims"][0]["scope"] = {"type": "organization-wide", "target": "all",
                                                                        "extent": "all"}
        self.assertTrue(any("wider" in e for e in self.check(adj)))


if __name__ == "__main__":
    unittest.main()
