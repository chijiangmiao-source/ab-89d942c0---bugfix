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


def _edge(id_, u, v, length=1):
    return {"id": id_, "u": u, "v": v, "length": length}


def _check_http_route(payload, r):
    """Recompute continuity, closure, copy coverage and positions from JSON."""
    assert r["ok"] is True
    start = r["start"]
    endpoints = {e["id"]: (e["u"], e["v"]) for e in r["edges"]}
    copies = {e["id"]: e["copies"] for e in r["edges"]}
    length_of = {e["id"]: e["length"] for e in r["edges"]}

    seen = {}
    cur = start
    total = 0
    for st in r["route"]:
        assert st["from"] == cur, st
        assert (st["from"], st["to"]) in {
            endpoints[st["edgeId"]], endpoints[st["edgeId"]][::-1]
        }
        seen.setdefault(st["edgeId"], []).append(
            (st["copy"], st["seq"], st["length"])
        )
        assert st["length"] == length_of[st["edgeId"]]
        total += st["length"]
        cur = st["to"]
    assert cur == start

    # every declared copy traversed exactly once, copies numbered 1..n
    for e in r["edges"]:
        occ = sorted(seen[e["id"]])
        assert [c for c, _, _ in occ] == list(range(1, copies[e["id"]] + 1))
        assert [s for _, s, _ in occ] == r["positions"][str(e["index"])]
    assert total == r["totalLength"] + r["addedLength"]
    assert len(r["route"]) == sum(copies.values())


K5_NODES = ["A", "B", "C", "D", "E"]

K5 = {
    "nodes": K5_NODES,
    "edges": [
        {"id": f"q{k:02d}", "u": a, "v": b, "length": 1}
        for k, (a, b) in enumerate(itertools.combinations(K5_NODES, 2))
    ],
    "start": "A",
}


def test_k5_complete_network_route_payload():
    r = run_audit(K5)
    assert r["ok"] is True
    assert r["eulerian"] is True
    assert r["totalLength"] == 10
    assert r["addedLength"] == 0
    assert r["optimalCount"] == 1
    assert r["canonicalVector"] == "0" * 10
    assert r["canonicalEdges"] == []
    # ten steps, not a seven-step partial loop
    assert len(r["route"]) == 10
    assert {st["edgeId"] for st in r["route"]} == {f"q{i:02d}" for i in range(10)}
    assert r["route"][0]["from"] == "A"
    assert r["route"][-1]["to"] == "A"
    # positions: exactly one step per edge, seq matches the route
    for e in r["edges"]:
        assert r["positions"][str(e["index"])] == [
            st["seq"] for st in r["route"] if st["edgeId"] == e["id"]
        ]
        assert len(r["positions"][str(e["index"])]) == 1
    _check_http_route(K5, r)


def test_augmented_network_positions_include_duplicate_copies():
    payload = {
        "nodes": ["A", "B", "C", "D"],
        "edges": [
            _edge("e1", "A", "B"), _edge("e2", "A", "C"),
            _edge("e3", "A", "D"), _edge("e4", "B", "C"),
            _edge("e5", "B", "D"), _edge("e6", "C", "D"),
        ],
        "start": "A",
    }
    r = run_audit(payload)
    assert r["ok"] is True
    assert r["addedLength"] == 2
    assert r["canonicalEdges"] == ["e3", "e4"]
    assert len(r["route"]) == 8
    by_id = {e["id"]: e for e in r["edges"]}
    assert by_id["e3"]["copies"] == 2 and by_id["e4"]["copies"] == 2
    assert len(r["positions"][str(by_id["e3"]["index"])]) == 2
    assert len(r["positions"][str(by_id["e4"]["index"])]) == 2
    _check_http_route(payload, r)


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
