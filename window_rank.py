#!/usr/bin/env python3
"""window-rank: SQL-ish ROW_NUMBER, RANK, and DENSE_RANK for a CSV.

Standard library only. Rows are ranked within an optional partition, ordered
by one or more columns. The original rows are written back with a rank column.
A JSON summary goes to stderr.
"""
import argparse
import csv
import json
import sys
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation


METHODS = ("row_number", "rank", "dense_rank")
DEFAULT_COL = {"row_number": "rn", "rank": "rank", "dense_rank": "dense_rank"}


def parse_cols(raw):
    if raw is None or raw.strip() == "":
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


class Desc:
    """Reverse a comparable value for descending sorts."""

    def __init__(self, value):
        self.value = value

    def __lt__(self, other):
        return self.value > other.value

    def __eq__(self, other):
        return self.value == other.value


def parse_sort_value(value):
    text = "" if value is None else str(value).strip()
    if text == "":
        return (1, 2, "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if isinstance(parsed, date) and not isinstance(parsed, datetime):
            parsed = datetime.combine(parsed, time.min)
        return (0, 0, parsed)
    except ValueError:
        pass
    try:
        return (0, 1, Decimal(text))
    except InvalidOperation:
        return (0, 2, text)


def order_key(row, order_cols, descending=False):
    parts = []
    for col in order_cols:
        blank, kind, val = parse_sort_value(row.get(col, ""))
        if descending and not blank:
            parts.append((blank, kind, Desc(val)))
        else:
            parts.append((blank, kind, val))
    return tuple(parts)


def rank_partition(items, method, order_cols, descending):
    """items is a list of (orig_index, row). Returns ranks by orig_index and tied_rows."""
    decorated = [
        (order_key(row, order_cols, descending), orig_index, row) for orig_index, row in items
    ]
    decorated.sort(key=lambda item: (item[0], item[1]))
    ranks = {}
    prev_key = None
    seen = 0
    current = 0
    tied_rows = 0
    group_size = 0
    for sort_key, orig_index, _row in decorated:
        seen += 1
        if sort_key != prev_key:
            if group_size > 1:
                tied_rows += group_size
            group_size = 1
            if method == "row_number":
                current = seen
            elif method == "rank":
                current = seen
            else:
                current = current + 1
            prev_key = sort_key
        else:
            group_size += 1
            if method == "row_number":
                current = seen
        ranks[orig_index] = current
    if group_size > 1:
        tied_rows += group_size
    return ranks, tied_rows


def rank_rows(rows, partition_cols, order_cols, method, descending):
    groups = {}
    for idx, row in enumerate(rows):
        if partition_cols:
            key = tuple(
                "" if row.get(col) is None else str(row.get(col)) for col in partition_cols
            )
        else:
            key = ()
        groups.setdefault(key, []).append((idx, row))

    ranks = {}
    tied_rows = 0
    for items in groups.values():
        part_ranks, part_ties = rank_partition(items, method, order_cols, descending)
        ranks.update(part_ranks)
        tied_rows += part_ties
    return ranks, len(groups), tied_rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Add a ROW_NUMBER, RANK, or DENSE_RANK column to a CSV, optionally partitioned."
    )
    parser.add_argument("path", help="input CSV")
    parser.add_argument(
        "--partition",
        default="",
        help="comma-separated partition columns (default: the whole file is one partition)",
    )
    parser.add_argument("--order", required=True, help="comma-separated order columns")
    parser.add_argument("--desc", action="store_true", help="sort each partition descending")
    parser.add_argument(
        "--method",
        choices=METHODS,
        default="row_number",
        help="ranking method (default: row_number)",
    )
    parser.add_argument(
        "--rank-col",
        metavar="NAME",
        help="name of the added rank column (default: rn, rank, or dense_rank)",
    )
    parser.add_argument(
        "--write",
        metavar="OUT",
        help="write the ranked CSV to OUT ('-' for stdout). Default: stdout",
    )
    args = parser.parse_args(argv)

    partition_cols = parse_cols(args.partition)
    order_cols = parse_cols(args.order)
    if not order_cols:
        print("window-rank: --order needs at least one column", file=sys.stderr)
        return 2
    rank_col = args.rank_col or DEFAULT_COL[args.method]

    try:
        with open(args.path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                print(f"window-rank: {args.path}: no header row", file=sys.stderr)
                return 2
            fields = list(reader.fieldnames)
            rows = list(reader)
    except OSError as exc:
        print(f"window-rank: {exc}", file=sys.stderr)
        return 2

    needed = partition_cols + order_cols
    missing = [col for col in needed if col not in fields]
    if missing:
        print(f"window-rank: missing columns: {', '.join(missing)}", file=sys.stderr)
        return 2
    if rank_col in fields:
        print(f"window-rank: rank column {rank_col!r} already exists", file=sys.stderr)
        return 2

    ranks, partitions, tied_rows = rank_rows(
        rows, partition_cols, order_cols, args.method, args.desc
    )
    out_fields = fields + [rank_col]
    out_rows = []
    for idx, row in enumerate(rows):
        out = dict(row)
        out[rank_col] = str(ranks[idx])
        out_rows.append(out)

    dest = args.write if args.write is not None else "-"
    try:
        if dest == "-":
            writer = csv.DictWriter(sys.stdout, fieldnames=out_fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(out_rows)
        else:
            with open(dest, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=out_fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(out_rows)
    except OSError as exc:
        print(f"window-rank: {exc}", file=sys.stderr)
        return 2

    report = {
        "path": args.path,
        "input_rows": len(rows),
        "output_rows": len(out_rows),
        "partition": partition_cols,
        "order": order_cols,
        "method": args.method,
        "rank_col": rank_col,
        "partitions": partitions,
        "tied_rows": tied_rows,
        "written": dest,
        "ok": True,
    }
    print(json.dumps(report, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
