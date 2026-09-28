"""CPU tests: routing reproduces the decisions printed in TypeSafe's guardrail cookbook."""

from replaykit.client import answers_hash, body_bytes
from tasks.guardrails.analyze import prf
from tasks.guardrails.battery import INPUT_BATTERY, POLICIES, assess, request, route

ZERO = {"jailbreak": 0.0, "harmful_request": 0.0, "medical_advice": 0.0, "self_harm": 0.0}


def nouls(**kw):
    return {**ZERO, **kw}


def test_cookbook_neurosemantical_policy_split():
    # Cookbook: "jailbreak=0.74, severity=0.51 -> strict block, permissive review"
    n = nouls(jailbreak=0.74)
    assert route(n, 0.51, POLICIES["strict"]) == "block"
    assert route(n, 0.51, POLICIES["permissive"]) == "review"


def test_cookbook_rows():
    strict = POLICIES["strict"]
    assert route(nouls(medical_advice=0.55), 0.3, strict) == "review"        # melatonin_dose
    assert route(nouls(medical_advice=0.95), 2.02, strict) == "block"        # dosage_request: severity upgrades
    assert route(nouls(self_harm=0.96), 2.4, strict) == "support"            # self_harm outranks block
    assert route(nouls(jailbreak=0.05), 0.8, strict) == "pass"               # novelist_poison
    assert route(nouls(harmful_request=0.95), 2.4, strict) == "block"        # lockpick_burglary


def test_threshold_edge_is_where_noise_matters():
    strict = POLICIES["strict"]
    assert route(nouls(jailbreak=0.70), 0.5, strict) == "block"
    assert route(nouls(jailbreak=0.69), 0.5, strict) == "review"
    assert route(nouls(jailbreak=0.34), 0.5, strict) == "pass"


def test_request_bytes_are_stable():
    a = body_bytes(request("hello", "jev-1.13.0"))
    b = body_bytes(request("hello", "jev-1.13.0"))
    assert a == b
    assert list(INPUT_BATTERY) == ["jailbreak", "harmful_request", "medical_advice", "self_harm", "severity"]


def test_assess_and_hash():
    answers = {q: {"type": "noul", "noul": 0.01} for q in ZERO} | {"severity": {"type": "score", "score": 0.0}}
    out = assess(answers)
    assert out["actions"] == {"strict": "pass", "permissive": "pass"}
    assert answers_hash(answers) == answers_hash(dict(reversed(list(answers.items()))))


def test_prf():
    m = prf([(True, True), (True, False), (False, True), (False, False)])
    assert m["recall"] == 0.5 and m["fpr"] == 0.5 and m["f1"] == 0.5
