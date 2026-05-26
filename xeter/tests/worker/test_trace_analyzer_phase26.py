"""Tests for TraceAnalyzer — Phase 26 proxy checks (RED scaffold).

Covers all 6 new check methods:
  - _check_wrong_agent_handoff       (TRACE-05)
  - _check_information_withholding   (TRACE-06)
  - _check_conversation_reset        (TRACE-07)
  - _check_clarification_skipped     (TRACE-08)
  - _check_no_verification           (TRACE-09)
  - _check_incomplete_verification   (TRACE-10)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from xeter.services.worker.trace_analyzer import TraceAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spans(n: int, **per_span_overrides) -> list:
    from xeter.services.worker.base import SpanData

    spans = []
    for i in range(n):
        fields = dict(
            span_id=f"s{i}",
            tenant_id="t1",
            trace_id="tr1",
            agent_name="ag",
            agent_model="gpt-4o",
            tool_name=None,
            tool_description=None,
            tool_arguments=None,
            tool_output=None,
            prompt=None,
            response=None,
            raw_response=None,
            available_tools=None,
        )
        for k, v in per_span_overrides.items():
            fields[k] = v[i] if isinstance(v, list) else v
        spans.append(SpanData(**fields))
    return spans


def _make_trace_analyzer(thresholds=None, routing_graph=None) -> TraceAnalyzer:
    mock_emb = MagicMock()
    mock_emb.encode.return_value = np.ones(384)
    mock_emb.encode_batch.return_value = [np.ones(384)]

    default_thresholds = {
        # Phase 25 (required for analyze() dispatch to existing checks)
        "stale_context": 85.0,
        "step_repetition": 85.0,
        "termination_loop_n": 3,
        "context_propagation_failure": 0.5,
        "history_loss": 0.4,
        # Phase 26
        "conversation_reset": 0.25,
        "information_withholding": 0.5,
        "wrong_agent_handoff": 1.0,
        "clarification_skipped": 1.0,
        "no_verification": 1.0,
        "incomplete_verification": 0.7,
    }
    if thresholds is not None:
        default_thresholds.update(thresholds)

    return TraceAnalyzer(mock_emb, default_thresholds, routing_graph=routing_graph)


# ---------------------------------------------------------------------------
# TRACE-05: wrong_agent_handoff
# ---------------------------------------------------------------------------


def test_wrong_agent_handoff_fires_when_transition_not_in_graph():
    routing_graph = {"orchestrator": ["search_agent"], "search_agent": ["orchestrator"]}
    ta = _make_trace_analyzer(routing_graph=routing_graph)
    # write_agent is NOT in orchestrator's allowed list
    spans = _make_spans(2, agent_name=["orchestrator", "write_agent"])
    flags = ta.analyze(spans)
    assert any(f.flag_type == "wrong_agent_handoff" for f in flags)


def test_wrong_agent_handoff_fires_when_source_not_in_graph():
    routing_graph = {"orchestrator": ["search_agent"]}
    ta = _make_trace_analyzer(routing_graph=routing_graph)
    # unknown_agent is NOT in the routing graph at all → flag
    spans = _make_spans(2, agent_name=["unknown_agent", "search_agent"])
    flags = ta.analyze(spans)
    assert any(f.flag_type == "wrong_agent_handoff" for f in flags)


def test_wrong_agent_handoff_no_flag_when_transition_is_valid():
    routing_graph = {"orchestrator": ["search_agent"], "search_agent": ["orchestrator"]}
    ta = _make_trace_analyzer(routing_graph=routing_graph)
    # orchestrator → search_agent is a valid transition
    spans = _make_spans(2, agent_name=["orchestrator", "search_agent"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "wrong_agent_handoff" for f in flags)


def test_wrong_agent_handoff_no_flag_when_routing_graph_is_none():
    ta = _make_trace_analyzer(routing_graph=None)
    spans = _make_spans(2, agent_name=["any_agent", "other_agent"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "wrong_agent_handoff" for f in flags)


def test_wrong_agent_handoff_detail_has_low_confidence_true():
    routing_graph = {"orchestrator": ["search_agent"]}
    ta = _make_trace_analyzer(routing_graph=routing_graph)
    spans = _make_spans(2, agent_name=["orchestrator", "write_agent"])
    flags = [f for f in ta.analyze(spans) if f.flag_type == "wrong_agent_handoff"]
    assert len(flags) > 0, "Expected at least one wrong_agent_handoff flag"
    assert flags[0].detail.get("low_confidence") is True


# ---------------------------------------------------------------------------
# TRACE-06: information_withholding
# ---------------------------------------------------------------------------


def _make_spacy_mock_with_entities(response_entities: list[str], prompt_entities: list[str]):
    """Return a mock nlp callable that returns ents based on the text passed."""
    def mock_nlp(text):
        doc = MagicMock()
        if text in response_entities or any(text == t for t in response_entities):
            # Return entities based on full text match
            pass
        # Build entity list based on text content
        ents = []
        for ent_text in response_entities:
            if ent_text.lower() in text.lower():
                ent = MagicMock()
                ent.text = ent_text
                ents.append(ent)
        # Separately, check prompt entities
        for ent_text in prompt_entities:
            if ent_text.lower() in text.lower():
                ent = MagicMock()
                ent.text = ent_text
                ents.append(ent)
        doc.ents = ents
        return doc
    return mock_nlp


def test_information_withholding_fires_when_entities_not_in_next_prompt():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        response=["Contact Alice Smith at ACME Corp", None],
        prompt=[None, "What is the weather?"],
    )

    # Create mock NLP: response has entities [Alice Smith, ACME Corp]; prompt has none
    mock_nlp = MagicMock()
    response_doc = MagicMock()
    alice_ent = MagicMock()
    alice_ent.text = "Alice Smith"
    acme_ent = MagicMock()
    acme_ent.text = "ACME Corp"
    response_doc.ents = [alice_ent, acme_ent]

    prompt_doc = MagicMock()
    prompt_doc.ents = []

    mock_nlp.side_effect = [response_doc, prompt_doc]

    with patch("xeter.services.worker.trace_analyzer._get_spacy", return_value=mock_nlp):
        flags = ta.analyze(spans)
    assert any(f.flag_type == "information_withholding" for f in flags)


def test_information_withholding_no_flag_when_entities_passed_through():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        response=["Alice Smith", None],
        prompt=[None, "Contact Alice Smith for details"],
    )

    mock_nlp = MagicMock()
    # Both response and prompt have the same entity
    alice_ent_resp = MagicMock()
    alice_ent_resp.text = "Alice Smith"
    response_doc = MagicMock()
    response_doc.ents = [alice_ent_resp]

    alice_ent_prompt = MagicMock()
    alice_ent_prompt.text = "Alice Smith"
    prompt_doc = MagicMock()
    prompt_doc.ents = [alice_ent_prompt]

    mock_nlp.side_effect = [response_doc, prompt_doc]

    with patch("xeter.services.worker.trace_analyzer._get_spacy", return_value=mock_nlp):
        flags = ta.analyze(spans)
    assert not any(f.flag_type == "information_withholding" for f in flags)


def test_information_withholding_no_flag_when_response_is_none():
    ta = _make_trace_analyzer()
    spans = _make_spans(2, response=[None, None], prompt=["some text", "other text"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "information_withholding" for f in flags)


def test_information_withholding_logs_score():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        response=["Alice Smith at ACME Corp", None],
        prompt=[None, "Some followup prompt"],
    )

    mock_nlp = MagicMock()
    alice_ent = MagicMock()
    alice_ent.text = "Alice Smith"
    response_doc = MagicMock()
    response_doc.ents = [alice_ent]
    prompt_doc = MagicMock()
    prompt_doc.ents = []

    mock_nlp.side_effect = [response_doc, prompt_doc]

    with patch("xeter.services.worker.trace_analyzer._get_spacy", return_value=mock_nlp):
        ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "information_withholding" for _, metric, _ in scores)


# ---------------------------------------------------------------------------
# TRACE-07: conversation_reset
# ---------------------------------------------------------------------------


def test_conversation_reset_fires_when_prompt_disconnected_abruptly():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    ta._embedder.encode.return_value = np.zeros(384)
    spans = _make_spans(3, prompt=["a", "b", "totally unrelated reset"])
    flags = ta.analyze(spans)
    assert any(f.flag_type == "conversation_reset" for f in flags)


def test_conversation_reset_no_flag_when_prompt_consistent():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    ta._embedder.encode.return_value = np.ones(384)  # cosine = 1.0, not < 0.25
    spans = _make_spans(3, prompt=["a", "b", "c"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "conversation_reset" for f in flags)


def test_conversation_reset_guard_fewer_than_3_spans():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    spans = _make_spans(2, prompt=["a", "b"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "conversation_reset" for f in flags)


def test_conversation_reset_detail_has_low_confidence_true():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    ta._embedder.encode.return_value = np.zeros(384)
    spans = _make_spans(3, prompt=["a", "b", "totally unrelated reset"])
    flags = [f for f in ta.analyze(spans) if f.flag_type == "conversation_reset"]
    assert len(flags) > 0, "Expected at least one conversation_reset flag"
    assert flags[0].detail.get("low_confidence") is True


def test_conversation_reset_logs_score():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode.return_value = np.ones(384)
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    spans = _make_spans(3, prompt=["a", "b", "c"])
    ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "conversation_reset" for _, metric, _ in scores)


# ---------------------------------------------------------------------------
# TRACE-08: clarification_skipped
# ---------------------------------------------------------------------------


def test_clarification_skipped_fires_when_disjunctive_prompt_no_question_in_response():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        1,
        prompt="Should we use approach A or approach B?",
        response="I will proceed with approach A.",
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "clarification_skipped" for f in flags)


def test_clarification_skipped_fires_for_either_keyword():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        1,
        prompt="Pick either the red or the blue option.",
        response="Going with red.",
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "clarification_skipped" for f in flags)


def test_clarification_skipped_no_flag_when_response_has_question_mark():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        1,
        prompt="Should we use A or B?",
        response="Could you clarify what you mean by A?",
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "clarification_skipped" for f in flags)


def test_clarification_skipped_no_flag_when_no_disjunctive_markers():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        1,
        prompt="Describe the process.",
        response="I will proceed step by step.",
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "clarification_skipped" for f in flags)


def test_clarification_skipped_detail_has_low_confidence_true():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        1,
        prompt="Should we use approach A or approach B?",
        response="I will proceed with approach A.",
    )
    flags = [f for f in ta.analyze(spans) if f.flag_type == "clarification_skipped"]
    assert len(flags) > 0, "Expected at least one clarification_skipped flag"
    assert flags[0].detail.get("low_confidence") is True


# ---------------------------------------------------------------------------
# TRACE-09: no_verification
# ---------------------------------------------------------------------------


def test_no_verification_fires_when_no_verification_tool_in_trace():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        tool_name=["search", "fetch"],
        tool_description=[None, None],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "no_verification" for f in flags)


def test_no_verification_no_flag_when_verify_keyword_in_tool_name():
    ta = _make_trace_analyzer()
    spans = _make_spans(2, tool_name=["search", "verify_output"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "no_verification" for f in flags)


def test_no_verification_no_flag_when_check_keyword_in_tool_description():
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        tool_name=["search", "audit"],
        tool_description=[None, "check the result for correctness"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "no_verification" for f in flags)


def test_no_verification_no_flag_when_validate_keyword_in_tool_name():
    ta = _make_trace_analyzer()
    spans = _make_spans(2, tool_name=["fetch", "validate_schema"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "no_verification" for f in flags)


def test_no_verification_keyword_match_is_case_insensitive():
    ta = _make_trace_analyzer()
    spans = _make_spans(2, tool_name=["search", "VERIFY_RESULT"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "no_verification" for f in flags)


# ---------------------------------------------------------------------------
# TRACE-10: incomplete_verification
# ---------------------------------------------------------------------------


def test_incomplete_verification_fires_when_entities_not_covered():
    ta = _make_trace_analyzer({"incomplete_verification": 0.7})
    # span[0] and span[1] are non-verification spans with responses containing entities
    # span[2] is a verification span (tool_name has "verify") with a narrow prompt
    spans = _make_spans(
        3,
        response=["Alice Smith at ACME Corp", "Project Orion", None],
        tool_name=[None, None, "verify_output"],
        prompt=[None, None, "Check Alice Smith"],
    )

    mock_nlp = MagicMock()

    # span[0].response → entities: alice_smith, acme_corp
    alice_ent = MagicMock()
    alice_ent.text = "Alice Smith"
    acme_ent = MagicMock()
    acme_ent.text = "ACME Corp"
    resp0_doc = MagicMock()
    resp0_doc.ents = [alice_ent, acme_ent]

    # span[1].response → entities: project_orion
    orion_ent = MagicMock()
    orion_ent.text = "Project Orion"
    resp1_doc = MagicMock()
    resp1_doc.ents = [orion_ent]

    # verification span[2].prompt → only alice_smith covered
    alice_ver_ent = MagicMock()
    alice_ver_ent.text = "Alice Smith"
    ver_doc = MagicMock()
    ver_doc.ents = [alice_ver_ent]

    # NLP called in order: resp[0], resp[1], then verification prompt
    mock_nlp.side_effect = [resp0_doc, resp1_doc, ver_doc]

    with patch("xeter.services.worker.trace_analyzer._get_spacy", return_value=mock_nlp):
        flags = ta.analyze(spans)
    assert any(f.flag_type == "incomplete_verification" for f in flags)


def test_incomplete_verification_no_flag_when_entities_well_covered():
    ta = _make_trace_analyzer({"incomplete_verification": 0.7})
    spans = _make_spans(
        2,
        response=["Alice Smith", None],
        tool_name=[None, "verify_output"],
        prompt=[None, "Check Alice Smith thoroughly"],
    )

    mock_nlp = MagicMock()

    alice_ent = MagicMock()
    alice_ent.text = "Alice Smith"
    resp_doc = MagicMock()
    resp_doc.ents = [alice_ent]

    alice_ver_ent = MagicMock()
    alice_ver_ent.text = "Alice Smith"
    ver_doc = MagicMock()
    ver_doc.ents = [alice_ver_ent]

    mock_nlp.side_effect = [resp_doc, ver_doc]

    with patch("xeter.services.worker.trace_analyzer._get_spacy", return_value=mock_nlp):
        flags = ta.analyze(spans)
    assert not any(f.flag_type == "incomplete_verification" for f in flags)


def test_incomplete_verification_skipped_when_no_verification_fires():
    """D-12 mutual exclusion: incomplete_verification skipped when no_verification fires."""
    ta = _make_trace_analyzer()
    # No verification keywords in any tool_name or tool_description → no_verification fires
    spans = _make_spans(
        2,
        tool_name=["search", "fetch"],
        tool_description=[None, None],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "incomplete_verification" for f in flags)


def test_no_verification_and_incomplete_verification_never_both_fire():
    ta = _make_trace_analyzer()
    # No verification keyword → no_verification fires; incomplete_verification must NOT
    spans = _make_spans(2, tool_name=["search", "fetch"], tool_description=["find", "retrieve"])
    flags = ta.analyze(spans)
    no_ver = [f for f in flags if f.flag_type == "no_verification"]
    inc_ver = [f for f in flags if f.flag_type == "incomplete_verification"]
    assert not (no_ver and inc_ver), "no_verification and incomplete_verification must not both fire"


def test_incomplete_verification_logs_score():
    ta = _make_trace_analyzer({"incomplete_verification": 0.7})
    spans = _make_spans(
        2,
        response=["Alice Smith", None],
        tool_name=[None, "verify_output"],
        prompt=[None, "Check Alice Smith"],
    )

    mock_nlp = MagicMock()

    alice_ent = MagicMock()
    alice_ent.text = "Alice Smith"
    resp_doc = MagicMock()
    resp_doc.ents = [alice_ent]

    alice_ver_ent = MagicMock()
    alice_ver_ent.text = "Alice Smith"
    ver_doc = MagicMock()
    ver_doc.ents = [alice_ver_ent]

    mock_nlp.side_effect = [resp_doc, ver_doc]

    with patch("xeter.services.worker.trace_analyzer._get_spacy", return_value=mock_nlp):
        ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "incomplete_verification" for _, metric, _ in scores)


def test_wrong_agent_handoff_same_agent_consecutive_no_flag():
    """Same agent consecutively is not a transition — should not fire wrong_agent_handoff."""
    routing_graph = {"orchestrator": ["search_agent"], "search_agent": ["orchestrator"]}
    ta = _make_trace_analyzer(routing_graph=routing_graph)
    # orchestrator → orchestrator: same agent, no handoff transition
    spans = _make_spans(2, agent_name=["orchestrator", "orchestrator"])
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "wrong_agent_handoff" for f in flags)
