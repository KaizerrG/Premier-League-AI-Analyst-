"""Eval harness for the Premier League AI analyst.

Usage:
    python run_eval.py --db pl_data.db --golden golden_set.json --min-acc 0.7

Metrics:
    answer_accuracy  - final answer contains every gold fact (names / numbers)
    exec_match       - generated SQL returns the same rows as the gold SQL
    exec_lenient     - generated SQL rows contain all gold values (extra columns OK)
    sql_valid        - generated SQL executes without error
    unsafe_sql       - generated SQL is not a single read-only SELECT
    error_rate       - the system crashed on the question
    latency p50/p95
"""
import argparse
import json
import re
import sqlite3
import statistics
import sys
import time
from collections import defaultdict


def run_system(question: str) -> dict:
    """Run one question through the project's public analyst entry point."""
    from graph import run_analyst

    return {"answer": run_analyst(question), "sql": None}


# ---------- helpers ----------
def norm(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, str):
        return v.strip().lower()
    return v


def fetch_rows(db, sql):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)  # read-only
    try:
        return [tuple(norm(x) for x in r) for r in con.execute(sql).fetchall()]
    finally:
        con.close()


def is_safe_select(sql):
    s = sql.strip().rstrip(";")
    if ";" in s:
        return False
    if not re.match(r"^\s*(select|with)\b", s, re.I):
        return False
    return not re.search(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace)\b", s, re.I)


def rows_match(gold, pred, ordered):
    if ordered:
        return gold == pred
    return sorted(map(repr, gold)) == sorted(map(repr, pred))


def rows_lenient(gold, pred):
    pred_sets = [set(r) for r in pred]
    return bool(gold) and all(any(set(g) <= p for p in pred_sets) for g in gold)


def answer_has_facts(gold_rows, answer):
    facts = [v for r in gold_rows[:10] for v in r]
    if not facts:
        return False
    nums = []
    for x in re.findall(r"-?\d[\d,]*\.?\d*", answer):
        try:
            nums.append(float(x.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    text = answer.lower()
    for f in facts:
        if isinstance(f, (int, float)):
            if not any(abs(n - f) <= 0.051 for n in nums):
                return False
        elif str(f) not in text:
            return False
    return True


# ---------- main ----------
def evaluate(db, golden):
    results = []
    for item in golden:
        t0 = time.time()
        try:
            out = run_system(item["question"])
            err = False
        except Exception as e:  # noqa: BLE001
            out, err = {"answer": "", "sql": None}, True
            print(f"[{item['id']}] system error: {e}", file=sys.stderr)
        latency = time.time() - t0

        answer, sql = out.get("answer", "") or "", out.get("sql")
        r = {"id": item["id"], "category": item["category"], "latency": latency,
             "error": err, "correct": False, "sql_valid": None,
             "exec_match": None, "exec_lenient": None, "unsafe_sql": False}

        if sql and not is_safe_select(sql):
            r["unsafe_sql"] = True

        if item["type"] == "sql":
            gold = fetch_rows(db, item["gold_sql"])
            r["correct"] = (not err) and answer_has_facts(gold, answer)
            if sql and not r["unsafe_sql"]:
                try:
                    pred = fetch_rows(db, sql)
                    r["sql_valid"] = True
                    r["exec_match"] = rows_match(gold, pred, item.get("ordered", False))
                    r["exec_lenient"] = rows_lenient(gold, pred)
                except sqlite3.Error:
                    r["sql_valid"] = False
                    r["exec_match"] = r["exec_lenient"] = False
        elif item["type"] == "refusal":
            r["correct"] = (not err) and bool(re.search(item["refusal_pattern"], answer, re.I)) \
                and not r["unsafe_sql"]
        results.append(r)
    return results


def pct(xs):
    xs = [x for x in xs if x is not None]
    return f"{100 * sum(xs) / len(xs):.1f}%" if xs else "n/a"


def report(results):
    lat = sorted(r["latency"] for r in results)
    p95 = lat[int(0.95 * (len(lat) - 1))]
    print(f"\nQuestions: {len(results)}")
    print(f"Answer accuracy : {pct([r['correct'] for r in results])}")
    print(f"Exec match      : {pct([r['exec_match'] for r in results])}")
    print(f"Exec lenient    : {pct([r['exec_lenient'] for r in results])}")
    print(f"SQL valid       : {pct([r['sql_valid'] for r in results])}")
    print(f"Unsafe SQL      : {sum(r['unsafe_sql'] for r in results)}")
    print(f"Error rate      : {pct([r['error'] for r in results])}")
    print(f"Latency p50/p95 : {statistics.median(lat):.2f}s / {p95:.2f}s")
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r["correct"])
    print("\nBy category (answer accuracy):")
    for cat, xs in sorted(by_cat.items()):
        print(f"  {cat:<12} {pct(xs):>7}  (n={len(xs)})")
    print("\nFailures:", [r["id"] for r in results if not r["correct"]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="pl_data.db")
    ap.add_argument("--golden", default="golden_set.json")
    ap.add_argument("--min-acc", type=float, default=0.0, help="exit 1 if answer accuracy is below this")
    ap.add_argument("--out", default="eval_report.json")
    args = ap.parse_args()

    with open(args.golden) as f:
        golden = json.load(f)
    results = evaluate(args.db, golden)
    report(results)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    acc = sum(r["correct"] for r in results) / len(results)
    sys.exit(0 if acc >= args.min_acc else 1)
