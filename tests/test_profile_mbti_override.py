"""Tests for the user-declared MBTI pin (profile overrides)."""

from __future__ import annotations

import pytest

from openbiliclaw.soul.overrides import (
    ProfileEditError,
    ProfileOverrides,
    apply_edit,
    apply_overrides,
    build_edit_state,
)
from openbiliclaw.soul.profile import MBTI, MBTIDimension, OnionProfile

INFJ = {
    "type": "INFJ",
    "identity": "A",
    "dimensions": {"EI": 0.54, "SN": 0.54, "TF": 0.68, "JP": 0.74},
    "confidence": 1.0,
    "source": "16Personalities 自测",
}


def _inferred_profile() -> OnionProfile:
    profile = OnionProfile()
    profile.core.mbti = MBTI(
        type="ISFJ",
        dimensions={
            "EI": MBTIDimension(pole="I", strength=0.75),
            "SN": MBTIDimension(pole="S", strength=0.80),
            "TF": MBTIDimension(pole="F", strength=0.58),
            "JP": MBTIDimension(pole="J", strength=0.65),
        },
        confidence=0.78,
        inferred_from=["行为推断"],
    )
    return profile


def test_declared_mbti_replaces_the_inference_and_survives_a_merge() -> None:
    overrides, result = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    assert result.ok is True

    effective = apply_overrides(_inferred_profile(), overrides)
    assert effective.core.mbti.type == "INFJ"
    assert effective.core.mbti.identity == "A"
    assert effective.core.mbti.confidence == 1.0
    # 四维用自测的百分比，极点按类型字母判断（I/N/F/J 是主导极）。
    assert effective.core.mbti.dimensions["EI"].pole == "I"
    assert effective.core.mbti.dimensions["EI"].strength == pytest.approx(0.54)
    assert effective.core.mbti.dimensions["SN"].pole == "N"
    assert effective.core.mbti.dimensions["TF"].pole == "F"
    assert effective.core.mbti.dimensions["JP"].strength == pytest.approx(0.74)
    assert effective.core.mbti.inferred_from == ["16Personalities 自测"]


def test_declared_mbti_is_not_mutated_by_later_inference() -> None:
    """The whole point: a core-layer rebuild must not win over the user's test."""

    overrides, _ = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    rebuilt = _inferred_profile()  # the LLM re-derives ISFJ
    assert apply_overrides(rebuilt, overrides).core.mbti.type == "INFJ"


def test_missing_dimensions_default_to_a_draw_and_other_axes_are_kept() -> None:
    overrides, _ = apply_edit(
        ProfileOverrides(),
        target="core.mbti",
        op="set",
        mbti={"type": "ENTP", "dimensions": {"EI": 0.7}},
    )
    pin = overrides.mbti_pin
    assert pin is not None
    assert pin.dimensions["EI"] == pytest.approx(0.7)
    assert pin.dimensions["SN"] == pytest.approx(0.6)
    effective = apply_overrides(_inferred_profile(), overrides)
    assert effective.core.mbti.dimensions["EI"].pole == "E"


def test_reset_returns_the_profile_to_the_inference() -> None:
    overrides, _ = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    cleared, result = apply_edit(overrides, target="core.mbti", op="reset")
    assert result.ok is True
    assert cleared.mbti_pin is None
    assert apply_overrides(_inferred_profile(), cleared).core.mbti.type == "ISFJ"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"type": "INF"}, "四个字母"),
        ({"type": "INFJX"}, "四个字母"),
        ({"type": "IXFJ"}, "四个字母"),
        ({"type": "INFJ", "identity": "B"}, "A 或 T"),
    ],
)
def test_invalid_declarations_are_rejected(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ProfileEditError) as excinfo:
        apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=payload)
    assert message in str(excinfo.value)


def test_mbti_only_supports_set_and_reset() -> None:
    with pytest.raises(ProfileEditError):
        apply_edit(ProfileOverrides(), target="core.mbti", op="add", mbti=INFJ)


def test_edit_state_exposes_the_pin_and_the_drifted_inference() -> None:
    overrides, _ = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    raw = _inferred_profile()
    effective = apply_overrides(raw, overrides)
    state = build_edit_state(raw, effective, overrides)
    field = state["fields"]["core.mbti"]
    assert field["type"] == "mbti"
    assert field["pinned"] is True
    assert field["value"]["type"] == "INFJ"
    assert field["value"]["identity"] == "A"
    assert field["value"]["source"] == "16Personalities 自测"
    assert field["ai_suggestion"]["type"] == "ISFJ"


def test_edit_state_has_no_drift_suggestion_when_the_model_agrees() -> None:
    overrides, _ = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    raw = _inferred_profile()
    raw.core.mbti.type = "INFJ"
    state = build_edit_state(raw, apply_overrides(raw, overrides), overrides)
    assert state["fields"]["core.mbti"]["ai_suggestion"] is None


def test_overrides_round_trip_through_json_payloads() -> None:
    overrides, _ = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    restored = ProfileOverrides.from_dict(overrides.to_dict())
    assert restored.mbti_pin is not None
    assert restored.mbti_pin.type == "INFJ"
    assert restored.mbti_pin.identity == "A"
    assert restored.mbti_pin.dimensions["JP"] == pytest.approx(0.74)
    assert restored.to_dict()["mbti_pin"]["source"] == "16Personalities 自测"


def test_overrides_without_a_pin_stay_empty() -> None:
    assert ProfileOverrides().is_empty() is True
    overrides, _ = apply_edit(ProfileOverrides(), target="core.mbti", op="set", mbti=INFJ)
    assert overrides.is_empty() is False
    cleared, _ = apply_edit(overrides, target="core.mbti", op="reset")
    assert cleared.is_empty() is True
