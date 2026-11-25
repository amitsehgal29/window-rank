#!/usr/bin/env python3
import csv
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal

import window_rank as wr


SAMPLES = os.path.join(os.path.dirname(__file__), "samples")
EVENTS = os.path.join(SAMPLES, "events.csv")


def run_main(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_out, old_err = wr.sys.stdout, wr.sys.stderr
    wr.sys.stdout, wr.sys.stderr = stdout, stderr
    try:
        code = wr.main(argv)
    finally:
        wr.sys.stdout, wr.sys.stderr = old_out, old_err
    err = stderr.getvalue()
    summary = json.loads(err) if err.strip().startswith("{") else None
    return code, stdout.getvalue(), summary, err


class HelperTests(unittest.TestCase):
    def test_parse_sort_value_types(self):
        self.assertEqual(wr.parse_sort_value("")[0], 1)
        self.assertEqual(wr.parse_sort_value("20"), (0, 1, Decimal("20")))
        kind = wr.parse_sort_value("2026-11-01T11:00:00")
        self.assertEqual(kind[1], 0)
        self.assertEqual(kind[2], datetime(2026, 11, 1, 11, 0, 0))

    def test_rank_partition_methods(self):
        rows = [
            (0, {"t": "a"}),
            (1, {"t": "b"}),
            (2, {"t": "b"}),
            (3, {"t": "c"}),
        ]
        rn, ties = wr.rank_partition(rows, "row_number", ["t"], False)
        self.assertEqual([rn[i] for i in range(4)], [1, 2, 3, 4])
        self.assertEqual(ties, 2)
        rk, _ties = wr.rank_partition(rows, "rank", ["t"], False)
        self.assertEqual([rk[i] for i in range(4)], [1, 2, 2, 4])
        dr, _ties = wr.rank_partition(rows, "dense_rank", ["t"], False)
        self.assertEqual([dr[i] for i in range(4)], [1, 2, 2, 3])


class CliTests(unittest.TestCase):
    def test_sample_row_number(self):
        code, out, summary, _err = run_main(
            [EVENTS, "--partition", "user_id", "--order", "event_time"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["input_rows"], 6)
        self.assertEqual(summary["partitions"], 2)
        self.assertEqual(summary["tied_rows"], 2)
        self.assertEqual(summary["method"], "row_number")
        rows = list(csv.DictReader(io.StringIO(out)))
        by_id = {row["event_id"]: row for row in rows}
        self.assertEqual(by_id["1"]["rn"], "1")
        self.assertEqual(by_id["2"]["rn"], "2")
        self.assertEqual(by_id["3"]["rn"], "3")
        self.assertEqual(by_id["4"]["rn"], "4")
        self.assertEqual(by_id["5"]["rn"], "1")
        self.assertEqual(by_id["6"]["rn"], "2")
        # original row order is preserved
        self.assertEqual([row["event_id"] for row in rows], ["1", "2", "3", "4", "5", "6"])

    def test_rank_and_dense_rank(self):
        code, out, summary, _err = run_main(
            [EVENTS, "--partition", "user_id", "--order", "event_time", "--method", "rank"]
        )
        self.assertEqual(code, 0)
        by_id = {row["event_id"]: row for row in csv.DictReader(io.StringIO(out))}
        self.assertEqual(by_id["2"]["rank"], "2")
        self.assertEqual(by_id["3"]["rank"], "2")
        self.assertEqual(by_id["4"]["rank"], "4")

        code, out, summary, _err = run_main(
            [
                EVENTS,
                "--partition",
                "user_id",
                "--order",
                "event_time",
                "--method",
                "dense_rank",
            ]
        )
        self.assertEqual(code, 0)
        by_id = {row["event_id"]: row for row in csv.DictReader(io.StringIO(out))}
        self.assertEqual(by_id["2"]["dense_rank"], "2")
        self.assertEqual(by_id["3"]["dense_rank"], "2")
        self.assertEqual(by_id["4"]["dense_rank"], "3")

    def test_desc_score_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "out.csv")
            code, out, summary, _err = run_main(
                [
                    EVENTS,
                    "--partition",
                    "user_id",
                    "--order",
                    "score",
                    "--desc",
                    "--rank-col",
                    "place",
                    "--write",
                    dest,
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            self.assertEqual(summary["written"], dest)
            with open(dest, newline="", encoding="utf-8") as handle:
                rows = {row["event_id"]: row for row in csv.DictReader(handle)}
            # u1 scores: 10,20,20,5 -> places 3, 1, 2 (stable on ties), 4? 
            # desc 20,20,10,5. Events 2 and 3 both score 20; stable by orig index: 2 then 3.
            self.assertEqual(rows["2"]["place"], "1")
            self.assertEqual(rows["3"]["place"], "2")
            self.assertEqual(rows["1"]["place"], "3")
            self.assertEqual(rows["4"]["place"], "4")
            self.assertEqual(rows["5"]["place"], "1")
            self.assertEqual(rows["6"]["place"], "2")

    def test_missing_and_existing_rank_col(self):
        code, _out, summary, err = run_main([EVENTS, "--partition", "missing", "--order", "event_time"])
        self.assertEqual(code, 2)
        self.assertIsNone(summary)
        self.assertIn("missing columns", err)

        code, _out, summary, err = run_main(
            [EVENTS, "--order", "event_time", "--rank-col", "event_id"]
        )
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)


if __name__ == "__main__":
    unittest.main()
