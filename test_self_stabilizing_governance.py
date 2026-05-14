# -*- coding: utf-8 -*-
# test_self_stabilizing_governance.py
# Phase 3.17 — Test suite for SelfStabilizingGovernanceEngine
# 28 test scenarios across 6 blocks

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_stable_context():
    return {
        "trajectory_stability": 0.95,
        "state_machine_coherence": 0.95,
        "orchestration_alignment": 0.95,
        "longitudinal_drift": 0.95,
        "strategy_alignment": 0.95,
        "pacing_overload_signal": 0.05,
        "load_balancing_overload": 0.05,
        "orchestration_queue_pressure": 0.05,
        "cognitive_load_score": 0.05,
        "dispatch_queue_depth_ratio": 0.05,
        "trajectory_coherence": 0.95,
        "state_machine_stability": 0.95,
        "longitudinal_coherence": 0.95,
        "adaptive_strategy_coherence": 0.95,
        "route_simulation_coherence": 0.95,
        "pacing_stability_score": 0.9,
        "pacing_pressure_level": 0.05,
        "pacing_queue_ratio": 0.05,
        "route_simulation_score": 0.85,
        "adaptive_strategy_score": 0.85,
        "route_simulation_state": "STABLE",
        "adaptive_strategy_state": "STABLE",
        "human_escalation_pathway_intact": True,
        "silence_respect_pathway_intact": True,
        "escalation_queue_health": 1.0,
        "silence_respected": True,
        "silence_bypass_detected": False,
        "silence_override_count": 0,
        "recovery_policy_applied": True,
        "recovery_policy_conflict": False,
        "recovery_policy_health": 1.0,
        "dispatcher_is_sole_outbound_path": True,
        "dispatcher_health": 1.0,
        "dispatcher_bypass_detected": False,
        "dispatcher_signal_integrity": 1.0,
    }


class TestStableBaseline:

    def test_stable_governance_state(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization(make_stable_context()))
        assert result["governance_stability_state"] == "STABLE_GOVERNANCE"
        assert result["stabilization_needed"] is False
        assert result["recommended_stabilization_mode"] == "no_change"
        assert result["is_neutral"] is False

    def test_all_scores_present(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization(make_stable_context()))
        required_keys = [
            "governance_drift_score", "overload_cascade_risk",
            "coherence_degradation_score", "pacing_pressure_stability",
            "route_conflict_stability", "escalation_stability_score",
            "silence_respect_integrity", "recovery_policy_integrity",
            "dispatcher_safety_alignment",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_all_scores_clamped_to_range(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization(make_stable_context()))
        for key in ["governance_drift_score", "overload_cascade_risk",
                    "coherence_degradation_score", "pacing_pressure_stability",
                    "route_conflict_stability", "escalation_stability_score",
                    "silence_respect_integrity", "recovery_policy_integrity",
                    "dispatcher_safety_alignment"]:
            val = result[key]
            assert 0.0 <= val <= 1.0, f"{key} out of range: {val}"

    def test_evaluated_at_present(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization(make_stable_context()))
        assert "evaluated_at" in result
        assert len(result["evaluated_at"]) > 0

    def test_stabilization_notes_list(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization(make_stable_context()))
        assert isinstance(result["stabilization_notes"], list)


class TestDriftAccumulation:

    def test_drift_accumulating_state(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["trajectory_stability"] = 0.4
        ctx["state_machine_coherence"] = 0.4
        ctx["orchestration_alignment"] = 0.4
        ctx["longitudinal_drift"] = 0.4
        ctx["strategy_alignment"] = 0.4
        result = run(evaluate_governance_stabilization(ctx))
        assert result["governance_stability_state"] in (
            "DRIFT_ACCUMULATING", "STABILIZATION_REQUIRED"
        )
        assert result["governance_drift_score"] > 0.4

    def test_drift_mode_is_valid(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["trajectory_stability"] = 0.45
        ctx["state_machine_coherence"] = 0.45
        ctx["orchestration_alignment"] = 0.45
        ctx["longitudinal_drift"] = 0.45
        ctx["strategy_alignment"] = 0.45
        result = run(evaluate_governance_stabilization(ctx))
        assert result["recommended_stabilization_mode"] in (
            "reduce_route_pressure", "protect_silence",
            "prioritize_recovery_policy", "hold_nonessential_actions",
            "escalate_for_human_review", "no_change", "maintain_current_governance",
        )


class TestOverloadCascade:

    def test_overload_cascade_state(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["pacing_overload_signal"] = 0.9
        ctx["load_balancing_overload"] = 0.9
        ctx["orchestration_queue_pressure"] = 0.9
        ctx["cognitive_load_score"] = 0.9
        ctx["dispatch_queue_depth_ratio"] = 0.9
        result = run(evaluate_governance_stabilization(ctx))
        assert result["governance_stability_state"] in (
            "OVERLOAD_CASCADE_RISK", "STABILIZATION_REQUIRED"
        )
        assert result["overload_cascade_risk"] > 0.6

    def test_cascade_mode_is_hold_or_reduce(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["pacing_overload_signal"] = 0.85
        ctx["load_balancing_overload"] = 0.85
        ctx["orchestration_queue_pressure"] = 0.85
        ctx["cognitive_load_score"] = 0.85
        ctx["dispatch_queue_depth_ratio"] = 0.85
        result = run(evaluate_governance_stabilization(ctx))
        assert result["recommended_stabilization_mode"] in (
            "hold_nonessential_actions", "reduce_dispatch_density",
            "escalate_for_human_review",
        )

    def test_cascade_stabilization_needed(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["pacing_overload_signal"] = 0.9
        ctx["load_balancing_overload"] = 0.9
        ctx["orchestration_queue_pressure"] = 0.9
        result = run(evaluate_governance_stabilization(ctx))
        assert result["stabilization_needed"] is True

    def test_cascade_notes_populated(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["pacing_overload_signal"] = 0.9
        ctx["load_balancing_overload"] = 0.9
        ctx["orchestration_queue_pressure"] = 0.9
        result = run(evaluate_governance_stabilization(ctx))
        assert len(result["stabilization_notes"]) > 0


class TestCoherenceDegradation:

    def test_coherence_degradation_state(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["trajectory_coherence"] = 0.2
        ctx["state_machine_stability"] = 0.2
        ctx["longitudinal_coherence"] = 0.2
        ctx["adaptive_strategy_coherence"] = 0.2
        ctx["route_simulation_coherence"] = 0.2
        result = run(evaluate_governance_stabilization(ctx))
        assert result["governance_stability_state"] in (
            "COHERENCE_DEGRADATION", "STABILIZATION_REQUIRED"
        )
        assert result["coherence_degradation_score"] > 0.5

    def test_pacing_pressure_low(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["pacing_stability_score"] = 0.3
        ctx["pacing_pressure_level"] = 0.8
        ctx["pacing_queue_ratio"] = 0.8
        result = run(evaluate_governance_stabilization(ctx))
        assert result["pacing_pressure_stability"] < 0.5

    def test_route_conflict_state(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["route_simulation_state"] = "CRITICAL"
        ctx["adaptive_strategy_state"] = "CONFLICT"
        ctx["route_simulation_score"] = 0.2
        ctx["adaptive_strategy_score"] = 0.8
        result = run(evaluate_governance_stabilization(ctx))
        assert result["route_conflict_stability"] < 0.5

    def test_route_conflict_mode(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["route_simulation_state"] = "CRITICAL"
        ctx["adaptive_strategy_state"] = "CONFLICT"
        ctx["route_simulation_score"] = 0.2
        ctx["adaptive_strategy_score"] = 0.9
        result = run(evaluate_governance_stabilization(ctx))
        assert result["recommended_stabilization_mode"] in (
            "stabilize_route_conflicts", "hold_nonessential_actions",
            "escalate_for_human_review",
        )


class TestGovernanceIntegrity:

    def test_silence_bypass_detected(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["silence_bypass_detected"] = True
        ctx["silence_respected"] = False
        result = run(evaluate_governance_stabilization(ctx))
        assert result["silence_respect_integrity"] < 0.5

    def test_silence_protect_mode(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["silence_bypass_detected"] = True
        ctx["silence_respected"] = False
        ctx["trajectory_stability"] = 0.45
        ctx["state_machine_coherence"] = 0.45
        ctx["orchestration_alignment"] = 0.45
        ctx["longitudinal_drift"] = 0.45
        ctx["strategy_alignment"] = 0.45
        result = run(evaluate_governance_stabilization(ctx))
        assert result["recommended_stabilization_mode"] in (
            "protect_silence", "escalate_for_human_review",
            "hold_nonessential_actions",
        )

    def test_recovery_policy_conflict(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["recovery_policy_conflict"] = True
        ctx["recovery_policy_applied"] = False
        ctx["recovery_policy_health"] = 0.2
        result = run(evaluate_governance_stabilization(ctx))
        assert result["recovery_policy_integrity"] < 0.5

    def test_escalation_instability(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["human_escalation_pathway_intact"] = False
        ctx["escalation_queue_health"] = 0.5
        result = run(evaluate_governance_stabilization(ctx))
        assert result["escalation_stability_score"] < 0.5

    def test_escalation_mode_is_human_review(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["human_escalation_pathway_intact"] = False
        ctx["escalation_queue_health"] = 0.2
        result = run(evaluate_governance_stabilization(ctx))
        assert result["recommended_stabilization_mode"] in (
            "escalate_for_human_review", "hold_nonessential_actions",
        )

    def test_dispatcher_bypass_detected(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["dispatcher_bypass_detected"] = True
        ctx["dispatcher_is_sole_outbound_path"] = False
        result = run(evaluate_governance_stabilization(ctx))
        assert result["dispatcher_safety_alignment"] < 0.3

    def test_stabilization_required_state(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        ctx = make_stable_context()
        ctx["dispatcher_bypass_detected"] = True
        ctx["dispatcher_is_sole_outbound_path"] = False
        ctx["dispatcher_health"] = 0.1
        result = run(evaluate_governance_stabilization(ctx))
        assert result["governance_stability_state"] == "STABILIZATION_REQUIRED"
        assert result["stabilization_needed"] is True


class TestFailSafeAndEdgeCases:

    def test_neutral_on_empty_context(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization({}))
        assert result["governance_stability_state"] in (
            "STABLE_GOVERNANCE", "UNKNOWN"
        )

    def test_neutral_on_none_context(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization(None))
        assert result["is_neutral"] is True
        assert result["governance_stability_state"] == "UNKNOWN"

    def test_neutral_on_string_context(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        result = run(evaluate_governance_stabilization("not a dict"))
        assert result["is_neutral"] is True

    def test_singleton_idempotency(self):
        from self_stabilizing_governance import (
            get_governance_stabilization_engine,
            SelfStabilizingGovernanceEngine,
        )
        SelfStabilizingGovernanceEngine._instance = None
        e1 = get_governance_stabilization_engine()
        e2 = get_governance_stabilization_engine()
        assert e1 is e2

    def test_evaluate_does_not_raise_on_mid_scores(self):
        from self_stabilizing_governance import (
            _determine_governance_state,
            _determine_stabilization_mode,
        )
        scores = {k: 0.5 for k in [
            "governance_drift_score", "overload_cascade_risk",
            "coherence_degradation_score", "pacing_pressure_stability",
            "route_conflict_stability", "escalation_stability_score",
            "silence_respect_integrity", "recovery_policy_integrity",
            "dispatcher_safety_alignment",
        ]}
        state = _determine_governance_state(scores)
        mode = _determine_stabilization_mode(state, scores)
        assert state in [
            "STABLE_GOVERNANCE", "DRIFT_ACCUMULATING", "OVERLOAD_CASCADE_RISK",
            "COHERENCE_DEGRADATION", "PACING_PRESSURE", "ROUTE_CONFLICT_PRESSURE",
            "ESCALATION_INSTABILITY", "STABILIZATION_REQUIRED", "UNKNOWN",
        ]
        assert mode in [
            "no_change", "reduce_route_pressure", "hold_nonessential_actions",
            "protect_silence", "prioritize_recovery_policy", "reduce_dispatch_density",
            "escalate_for_human_review", "stabilize_route_conflicts",
            "maintain_current_governance",
        ]

    def test_clamp_function(self):
        from self_stabilizing_governance import _clamp
        assert _clamp(-1.0) == 0.0
        assert _clamp(2.0) == 1.0
        assert _clamp(0.5) == 0.5
        assert _clamp("bad") == 0.0

    def test_neutral_result_structure(self):
        from self_stabilizing_governance import _neutral_result
        result = _neutral_result()
        assert result["is_neutral"] is True
        assert result["governance_stability_state"] == "UNKNOWN"
        assert result["stabilization_needed"] is False
        assert result["recommended_stabilization_mode"] == "no_change"
        assert isinstance(result["stabilization_notes"], list)

    def test_all_governance_states_reachable(self):
        from self_stabilizing_governance import _determine_governance_state
        scores_stable = {k: 0.0 for k in [
            "governance_drift_score", "overload_cascade_risk", "coherence_degradation_score"]}
        scores_stable.update({k: 0.9 for k in [
            "pacing_pressure_stability", "route_conflict_stability",
            "escalation_stability_score", "silence_respect_integrity",
            "recovery_policy_integrity", "dispatcher_safety_alignment"]})
        assert _determine_governance_state(scores_stable) == "STABLE_GOVERNANCE"

        scores_esc = dict(scores_stable)
        scores_esc["escalation_stability_score"] = 0.4
        assert _determine_governance_state(scores_esc) == "ESCALATION_INSTABILITY"

        scores_cascade = dict(scores_stable)
        scores_cascade["overload_cascade_risk"] = 0.7
        assert _determine_governance_state(scores_cascade) == "OVERLOAD_CASCADE_RISK"

        scores_coh = dict(scores_stable)
        scores_coh["coherence_degradation_score"] = 0.6
        assert _determine_governance_state(scores_coh) == "COHERENCE_DEGRADATION"

        scores_drift = dict(scores_stable)
        scores_drift["governance_drift_score"] = 0.5
        assert _determine_governance_state(scores_drift) == "DRIFT_ACCUMULATING"

    def test_all_stabilization_modes_reachable(self):
        from self_stabilizing_governance import _determine_stabilization_mode
        assert _determine_stabilization_mode("STABLE_GOVERNANCE", {}) == "no_change"
        assert _determine_stabilization_mode("ESCALATION_INSTABILITY", {}) == "escalate_for_human_review"
        assert _determine_stabilization_mode("OVERLOAD_CASCADE_RISK", {}) == "hold_nonessential_actions"
        assert _determine_stabilization_mode("ROUTE_CONFLICT_PRESSURE", {}) == "stabilize_route_conflicts"
        scores = {"silence_respect_integrity": 0.3, "recovery_policy_integrity": 0.9}
        assert _determine_stabilization_mode("DRIFT_ACCUMULATING", scores) == "protect_silence"

    def test_evaluate_with_partial_context(self):
        from self_stabilizing_governance import evaluate_governance_stabilization
        partial_ctx = {
            "pacing_overload_signal": 0.5,
            "silence_respected": False,
        }
        result = run(evaluate_governance_stabilization(partial_ctx))
        assert "governance_stability_state" in result
        assert 0.0 <= result.get("governance_drift_score", 0.0) <= 1.0
