"""Exercises the LLM code path with a fake Instructor client.

This proves the wiring (structured calls, verbatim filtering, reconciliation
against the deterministic read, dual-judge AND, fallback on failure) without a
network. It is not a substitute for a run against a live key; see README.
"""
from agents import CertoPipeline, LLMClient, _EventList, _GapList, _Redline
from mock_data import SAMPLE_CONTRACT, SEED_EVENTS, TX_342_203_TEXT
from schemas import ComplianceGap, GroundingVerdict, RegulatoryEvent


class FakeInstructor:
    """Returns canned objects per response_model; records what it was asked."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    class _Chat:
        def __init__(self, outer):
            self.completions = self

            self.outer = outer

        def create(self, **kw):
            self.outer.calls.append(kw["response_model"].__name__)
            return self.outer.behaviour(kw["response_model"], kw["messages"][-1]["content"])

    @property
    def chat(self):
        return FakeInstructor._Chat(self)


def _client(behaviour):
    return LLMClient("openai", "fake-model", FakeInstructor(behaviour))


def test_extractor_llm_events_are_filtered_and_reconciled():
    def behaviour(model, prompt):
        assert model is _EventList
        return _EventList(events=[
            RegulatoryEvent(  # verbatim snippet, wrong threshold: deterministic read must win
                event_id="", jurisdiction="TX", agency="x", statute_citation="Tex. Fin. Code § 342.203(d)",
                effective_date="1999-09-01", rule_type="FEE_CAP", summary="s",
                raw_source_snippet="The additional interest may not exceed five cents for each $1 of a scheduled installment.",
                numerical_threshold=15.0, threshold_unit="USD",
            ),
            RegulatoryEvent(  # hallucinated snippet: must be dropped
                event_id="", jurisdiction="TX", agency="x", statute_citation="Tex. Fin. Code § 342.999",
                effective_date="1999-09-01", rule_type="FEE_CAP", summary="s",
                raw_source_snippet="A lender may charge whatever it likes.", numerical_threshold=99.0, threshold_unit="USD",
            ),
        ])

    p = CertoPipeline(_client(behaviour))
    events, mode = p.extractor.run("TX", "OCCC", TX_342_203_TEXT, code_name="Tex. Fin. Code")
    assert mode == "llm"
    assert [e.statute_citation for e in events] == ["Tex. Fin. Code § 342.203(d)"]
    assert events[0].numerical_threshold == 5.0 and events[0].threshold_unit == "PERCENT_OF_INSTALLMENT"
    assert events[0].fee_cap and events[0].fee_cap.pct_max == 5.0
    assert events[0].event_id


def test_gap_engine_keeps_deterministic_and_filters_llm_gaps():
    def behaviour(model, prompt):
        assert model is _GapList
        return _GapList(gaps=[
            ComplianceGap(  # points at a real clause and citation, not found deterministically: kept at capped confidence
                gap_id="", severity="WARNING", statute_citation="Cal. Fin. Code § 22337(a)", target_clause_id="cl-16",
                target_clause_text="ignored", violation_reason="Notices clause lacks license number", statutory_threshold_violated=None,
                suggested_patch="Add the license number per Cal. Fin. Code § 22337(a).", confidence_score=0.99,
                is_grounded_in_citation=True, jurisdiction="CA", rule_type="DISCLOSURE_MANDATE",
            ),
            ComplianceGap(  # invented clause: dropped
                gap_id="", severity="CRITICAL", statute_citation="Cal. Fin. Code § 22337(a)", target_clause_id="cl-999",
                target_clause_text="x", violation_reason="x", statutory_threshold_violated=None, suggested_patch="x",
                confidence_score=0.9, is_grounded_in_citation=False, jurisdiction="CA", rule_type="DISCLOSURE_MANDATE",
            ),
            ComplianceGap(  # invented citation: dropped
                gap_id="", severity="CRITICAL", statute_citation="Cal. Fin. Code § 99999", target_clause_id="cl-5",
                target_clause_text="x", violation_reason="x", statutory_threshold_violated=None, suggested_patch="x",
                confidence_score=0.9, is_grounded_in_citation=False, jurisdiction="CA", rule_type="FEE_CAP",
            ),
        ])

    p = CertoPipeline(_client(behaviour))
    gaps, mode = p.gap_engine.run(SAMPLE_CONTRACT, SEED_EVENTS)
    assert mode == "llm"
    det_gaps, _ = CertoPipeline(None).gap_engine.run(SAMPLE_CONTRACT, SEED_EVENTS)
    assert {g.gap_id for g in det_gaps} <= {g.gap_id for g in gaps}
    extra = [g for g in gaps if g.gap_id not in {d.gap_id for d in det_gaps}]
    assert len(extra) == 1 and extra[0].target_clause_id == "cl-16" and extra[0].confidence_score == 0.8
    assert extra[0].target_clause_text.startswith("15. Notices")


def test_remediator_reverts_ungrounded_llm_redline_and_ands_the_judges():
    det_gaps, _ = CertoPipeline(None).gap_engine.run(SAMPLE_CONTRACT, SEED_EVENTS)
    gap = next(g for g in det_gaps if g.statute_citation == "Tex. Fin. Code § 342.203(d)")
    event = next(e for e in SEED_EVENTS if e.statute_citation == gap.statute_citation)

    def bad_drafter(model, prompt):
        if model is _Redline:
            return _Redline(redlined_text="Late charge shall be $99 or 40% of the payment under Tex. Fin. Code § 342.203(d).", change_rationale="wrong")
        return GroundingVerdict(is_grounded=True, cited_statute_present=True, numbers_match_statute=True, no_invented_obligations=True, judge_rationale="llm says fine", confidence=0.9)

    patch = CertoPipeline(_client(bad_drafter)).remediator.run(gap, SAMPLE_CONTRACT, event)
    assert patch.redlined_text == gap.suggested_patch  # deterministic judge rejected the LLM draft
    assert patch.grounding.is_grounded is True
    assert "LLM judge" in patch.grounding.judge_rationale

    def strict_llm_judge(model, prompt):
        if model is _Redline:
            return _Redline(redlined_text=gap.suggested_patch, change_rationale="same as deterministic")
        return GroundingVerdict(is_grounded=False, cited_statute_present=True, numbers_match_statute=True, no_invented_obligations=False, judge_rationale="llm objects", confidence=0.7)

    patch = CertoPipeline(_client(strict_llm_judge)).remediator.run(gap, SAMPLE_CONTRACT, event)
    assert patch.grounding.is_grounded is False  # both judges must agree
    assert patch.grounding.confidence == 0.7


def test_llm_failure_falls_back_to_deterministic():
    def boom(model, prompt):
        raise RuntimeError("provider down")

    p = CertoPipeline(_client(boom))
    events, mode = p.extractor.run("TX", "OCCC", TX_342_203_TEXT, code_name="Tex. Fin. Code")
    assert mode == "deterministic" and events
    gaps, mode = p.gap_engine.run(SAMPLE_CONTRACT, SEED_EVENTS)
    assert mode == "deterministic" and gaps
