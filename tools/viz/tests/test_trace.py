# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from viz.trace import RunTrace, join_lanes


def lane(lane_id, t_start, t_end, ue=None, rnti=None, label=None, open_=False):
    return {"lane": lane_id, "t_start": t_start, "t_end": t_end, "ue": ue, "rnti": rnti, "label": label, "open": open_}


def event(t, lane_id, category="rrc", ev_type="x"):
    return {"t": t, "record": int(t * 10), "type": ev_type, "category": category, "lane": lane_id, "ue": None, "rnti": None}


class FakeStore:
    """Store with fixed lanes and events, filtered by time window like Store.trace()."""

    def __init__(self, lanes, events):
        self._lanes, self._events = lanes, events

    def trace(self, t0, t1, max_lanes, limit):
        lo = -float("inf") if t0 is None else t0
        hi = float("inf") if t1 is None else t1
        events = [e for e in self._events if lo <= e["t"] <= hi]
        return {"lanes": self._lanes[:max_lanes], "events": events[:limit]}


# F1AP UE contexts: a UE attaching at 10 s, handed over at 20 s to a new context with C-RNTI 0x4602.
F1AP = FakeStore(
    [lane(0, 10.0, 20.5, rnti="0x4601", label="du_f1ap=0 cu_f1ap=0"), lane(1, 20.0, 30.0, rnti="0x4602", label="du_f1ap=1 cu_f1ap=1")],
    [event(9.0, None, "f1ap", "F1Setup"), event(10.0, 0), event(20.0, 1, "f1ap", "UEContextSetup")],
)
# Log lanes: the random access and creation of the first UE, the handover target created without RNTI, its
# contention-free random access with the RNTI only, and a UE of no F1AP context.
LOG = FakeStore(
    [
        lane(0, 9.9, 20.5, ue=0, rnti="0x4601"),
        lane(1, 20.001, 30.0, ue=1),
        lane(2, 20.1, 20.1, rnti="0x4602"),
        lane(3, 50.0, 51.0, ue=5, rnti="0x4609"),
    ],
    [event(9.9, 0, "ra", "prach"), event(20.001, 1, "lifecycle", "ue_create"), event(20.1, 2, "ra", "prach"),
     event(50.0, 3, "ra", "prach"), event(60.0, None, "warning", "warning")],
)


class JoinTest(unittest.TestCase):
    def test_join_lanes(self):
        lanes = join_lanes((7, F1AP), [(3, LOG)])
        self.assertEqual([(lane.key, lane.parts) for lane in lanes], [
            ("7:0", [(7, 0), (3, 0)]),
            ("7:1", [(7, 1), (3, 1), (3, 2)]),
            ("3:3", [(3, 3)]),
        ])
        first, target, unjoined = lanes
        # The log lanes widen their context, e.g. with the random access before the first F1AP message.
        self.assertEqual((first.t_start, first.ue), (9.9, 0))
        self.assertEqual((target.ue, target.rnti, target.label), (1, "0x4602", "du_f1ap=1 cu_f1ap=1"))
        self.assertEqual((unjoined.ue, unjoined.rnti, unjoined.label), (5, "0x4609", None))

    def test_rnti_outside_the_context_does_not_join(self):
        late = FakeStore([lane(0, 40.0, 41.0, rnti="0x4601")], [])
        self.assertEqual([lane.key for lane in join_lanes((7, F1AP), [(3, late)])], ["7:0", "7:1", "3:0"])

    def test_trace(self):
        trace = RunTrace((7, F1AP), [(3, LOG)]).trace(None, None, 300, 100)
        self.assertEqual(trace["total_lanes"], 3)
        by_type = {e["type"]: (e["source"], e["lane"]) for e in trace["events"]}
        self.assertEqual(by_type["F1Setup"], (7, None))
        self.assertEqual(by_type["ue_create"], (3, "7:1"))
        self.assertEqual(by_type["prach"], (3, "3:3"))
        self.assertEqual(by_type["warning"], (3, None))

    def test_log_rrc_left_out_with_the_f1ap_pcap(self):
        log = FakeStore([lane(0, 9.9, 20.5, ue=0, rnti="0x4601")], [event(10.1, 0, "rrc", "rrc_setup_complete"), event(10.2, 0, "ra", "conres")])
        joined = RunTrace((7, F1AP), [(3, log)])
        self.assertEqual([e["type"] for e in joined.trace(None, None, 300, 100)["events"] if e["source"] == 3], ["conres"])
        log_only = joined.trace(None, None, 300, 100, {3})["events"]
        self.assertEqual([e["type"] for e in log_only], ["rrc_setup_complete", "conres"])

    def test_trace_of_one_source(self):
        trace = RunTrace((7, F1AP), [(3, LOG)]).trace(None, None, 300, 100, {3})
        # The lanes of the log only, the F1AP contexts it joined and its own.
        self.assertEqual([lane["lane"] for lane in trace["lanes"]], ["7:0", "7:1", "3:3"])
        self.assertEqual({e["source"] for e in trace["events"]}, {3})
        self.assertEqual({e["type"]: e["lane"] for e in trace["events"]}["ue_create"], "7:1")

    def test_trace_window_and_limits(self):
        trace = RunTrace((7, F1AP), [(3, LOG)]).trace(19.0, 25.0, 1, 100)
        self.assertEqual(([lane["lane"] for lane in trace["lanes"]], trace["total_lanes"]), (["7:0"], 2))
        # Events of lanes beyond max_lanes are left out, like Store.trace().
        self.assertEqual([e["type"] for e in trace["events"]], [])
        trace = RunTrace((7, F1AP), [(3, LOG)]).trace(None, None, 300, 2)
        self.assertEqual((len(trace["events"]), trace["total_events"], trace["truncated"]), (2, 8, True))


if __name__ == "__main__":
    unittest.main()
