# window-rank

SQL-ish `ROW_NUMBER`, `RANK`, and `DENSE_RANK` for a CSV.

Rows are ranked within an optional partition, ordered by one or more
columns. Timestamps, numbers, and strings are detected automatically.
The original row order is kept, with a new rank column appended.
Ties share a rank for `rank` and `dense_rank`; `rank` then skips the
next numbers (`1, 2, 2, 4`) while `dense_rank` does not (`1, 2, 2, 3`).
A JSON summary is printed to stderr.

Standard library only. Requires Python 3.

## How to run

```bash
python3 window_rank.py samples/events.csv --partition user_id --order event_time --method rank
```

Use `row_number` (the default), sort descending, or write to a file:

```bash
python3 window_rank.py samples/events.csv --partition user_id --order event_time
python3 window_rank.py samples/events.csv --partition user_id --order score --desc --rank-col place --write ranked.csv
```

Run the tests:

```bash
python3 -m unittest -v
```

## Example output

From a real run of

`python3 window_rank.py samples/events.csv --partition user_id --order event_time --method rank`.

The JSON is written to stderr; the CSV is written to stdout.

```
{
  "path": "samples/events.csv",
  "input_rows": 6,
  "output_rows": 6,
  "partition": [
    "user_id"
  ],
  "order": [
    "event_time"
  ],
  "method": "rank",
  "rank_col": "rank",
  "partitions": 2,
  "tied_rows": 2,
  "written": "-",
  "ok": true
}
event_id,user_id,event_time,score,rank
1,u1,2026-11-01T10:00:00,10,1
2,u1,2026-11-01T11:00:00,20,2
3,u1,2026-11-01T11:00:00,20,2
4,u1,2026-11-01T12:00:00,5,4
5,u2,2026-11-01T09:00:00,50,1
6,u2,2026-11-01T10:30:00,40,2
```

Events 2 and 3 for `u1` share the same `event_time`, so they both get rank 2
and the next row is rank 4. `tied_rows` is 2 for that pair.
