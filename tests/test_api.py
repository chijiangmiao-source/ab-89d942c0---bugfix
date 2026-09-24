"""Tests for the HTTP-facing serialization layer (pure, no server needed)."""

import itertools

from app.server import run_audit


K4 = {
    "nodes": ["A", "B", "C", "D"],
    "edges": [
        {"id": "e1", "u": "A", "v": "B", "length": 1},
        {"id": "e2", "u": "A", "v": "C", "length": 1},
        {"id": "e3", "u": "A", "v": "D", "length": 1},
        {"id": "e4", "u": "B", "v": "C", "length": 1},
        {"id": "e5", "u": "B", "v": "D", "length": 1},
        {"id": "e6", "u": "C", "v": "D", "length": 1},
    ],
    "start": "A",
}


def test_success_payload():
    r = run_audit(K4)
    assert r["ok"] is True
    assert r["optimalCount"] == 3
    assert r["addedLength"] == 2
    assert r["totalLength"] == 6
    assert r["canonicalVector"] == "001100"
    assert r["canonicalEdges"] == ["e3", "e4"]
    assert len(r["route"]) == 8
    # positions cover exactly duplicated canonical edges' extra copies
    counts = {e["id"]: len(r["positions"][str(e["index"])]) for e in r["edges"]}
    duplicated = set(r["canonicalEdges"])
    for eid, n in counts.items():
        assert n == (2 if eid in duplicated else 1)
    # route closes at start
    assert r["route"][0]["from"] == "A"
    assert r["route"][-1]["to"] == "A"


def test_eulerian_payload():
    payload = {
        "nodes": ["A", "B", "C"],
        "edges": [
            {"id": "a", "u": "A", "v": "B", "length": 3},
            {"id": "b", "u": "B", "v": "C", "length": 4},
            {"id": "c", "u": "C", "v": "A", "length": 5},
        ],
        "start": "B",
    }
    r = run_audit(payload)
    assert r["ok"]
    assert r["eulerian"] is True
    assert r["addedLength"] == 0
    assert r["optimalCount"] == 1
    assert r["canonicalVector"] == "000"
    assert r["canonicalEdges"] == []
    assert all(e["classification"] == "never" for e in r["edges"])


def _check_route_payload(r, start):
    """Step-by-step route reconciliation against the summary fields."""
    route = r["route"]
    # continuity and closure at the inspection port
    assert route[0]["from"] == start
    for prev, nxt in zip(route, route[1:]):
        assert prev["to"] == nxt["from"]
    assert route[-1]["to"] == start
    # sequence numbers are 1..N and lengths reconcile with the summary
    assert [s["seq"] for s in route] == list(range(1, len(route) + 1))
    assert sum(s["length"] for s in route) == (
        r["totalLength"] + r["addedLength"]
    )
    # positions: every copy of every edge appears at exactly the steps listed
    flat = []
    for e in r["edges"]:
        ps = r["positions"][str(e["index"])]
        assert len(ps) == e["copies"]
        for p in ps:
            st = route[p - 1]
            assert st["edgeId"] == e["id"] and st["edgeIndex"] == e["index"]
        flat.extend(ps)
    assert sorted(flat) == list(range(1, len(route) + 1))


def test_k5_complete_network_payload():
    payload = {
        "nodes": list("ABCDE"),
        "edges": [
            {"id": f"q{i:02d}", "u": a, "v": b, "length": 1}
            for i, (a, b) in enumerate(itertools.combinations("ABCDE", 2))
        ],
        "start": "A",
    }
    r = run_audit(payload)
    assert r["ok"] is True
    assert r["eulerian"] is True
    assert r["totalLength"] == 10
    assert r["addedLength"] == 0
    assert r["optimalCount"] == 1
    assert r["canonicalVector"] == "0000000000"
    assert r["canonicalEdges"] == []
    assert len(r["route"]) == 10
    # each of the ten pipes is walked exactly once
    assert sorted(s["edgeId"] for s in r["route"]) == [
        e["id"] for e in payload["edges"]
    ]
    assert all(e["copies"] == 1 for e in r["edges"])
    _check_route_payload(r, "A")


def test_duplicate_copies_payload():
    # non-Eulerian: canonical set duplicates q6, so the route has 8 steps
    # and q6 must show up twice with copy numbers 1 and 2
    payload = {
        "nodes": list("ABCDE"),
        "edges": [
            {"id": "q0", "u": "A", "v": "B", "length": 1},
            {"id": "q1", "u": "B", "v": "C", "length": 1},
            {"id": "q2", "u": "C", "v": "A", "length": 1},
            {"id": "q3", "u": "B", "v": "D", "length": 1},
            {"id": "q4", "u": "D", "v": "E", "length": 1},
            {"id": "q5", "u": "E", "v": "B", "length": 1},
            {"id": "q6", "u": "D", "v": "E", "length": 1},
        ],
        "start": "A",
    }
    r = run_audit(payload)
    assert r["ok"] is True
    assert r["eulerian"] is False
    assert r["addedLength"] == 1
    assert r["canonicalEdges"] == ["q6"]
    assert len(r["route"]) == 8
    q6_steps = [s for s in r["route"] if s["edgeId"] == "q6"]
    assert sorted(s["copy"] for s in q6_steps) == [1, 2]
    _check_route_payload(r, "A")


def test_failure_payload_locations():
    r = run_audit({"nodes": ["A", "B"],
                   "edges": [{"id": "x", "u": "A", "v": "Z", "length": 1}],
                   "start": "A"})
    assert r["ok"] is False
    assert "edges" in r["fields"]
    assert r["locations"][0]["row"] == 0

    r = run_audit({"nodes": ["A", "B"],
                   "edges": [{"id": "x", "u": "A", "v": "B", "length": -2}],
                   "start": "A"})
    assert not r["ok"] and "正整数" in r["error"]

    r = run_audit({"nodes": ["A", "B"],
                   "edges": [{"id": "x", "u": "A", "v": "B", "length": 1}],
                   "start": "Q"})
    assert not r["ok"] and r["fields"] == ["start"]

    r = run_audit({"nodes": ["A", "B", "C"],
                   "edges": [{"id": "x", "u": "A", "v": "B", "length": 1}],
                   "start": "A"})
    assert not r["ok"] and "不连通" in r["error"]


def test_malformed_payload_is_safe():
    assert run_audit({})["ok"] is False
    assert run_audit({"nodes": "ab", "edges": None})["ok"] is False
