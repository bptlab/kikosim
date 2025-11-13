#!/usr/bin/env python3
"""
Analyze OrderManagement sequences exported to backend/ordermanagement_sequences_latest.csv.

Outputs:
- Coverage of 34 canonical BSPL sequences
- Counts per matched sequence
- List of non-terminal cases (if any)
"""
import pandas as pd
from pathlib import Path

SEQ_FILE = Path(__file__).parent / "ordermanagement_sequences_latest.csv"

# Canonical sequences (spaces optional; we compare normalized tokens)
CANON = [
    "B>S:order, S>B:reject",
    "B>S:order, S>B:invoice, B>S:pay, B>S:cancel_req, S>B:cancel_ack",
    "B>S:order, S>B:invoice, B>S:pay, B>S:cancel_req, S>L:delivery_req, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, B>S:pay, S>L:delivery_req, B>S:cancel_req, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, B>S:pay, S>L:delivery_req, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, B>S:cancel_req, B>S:pay, S>B:cancel_ack",
    "B>S:order, S>B:invoice, B>S:cancel_req, B>S:pay, S>L:delivery_req, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, B>S:cancel_req, S>B:cancel_ack",
    "B>S:order, S>B:invoice, B>S:cancel_req, S>L:delivery_req, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, B>S:cancel_req, S>L:delivery_req, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, S>B:invoice, S>L:delivery_req, B>S:pay, B>S:cancel_req, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, S>L:delivery_req, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, S>L:delivery_req, B>S:cancel_req, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, S>B:invoice, S>L:delivery_req, B>S:cancel_req, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, S>B:invoice, S>L:delivery_req, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, B>S:cancel_req, S>B:reject",
    "B>S:order, B>S:cancel_req, S>B:invoice, B>S:pay, S>B:cancel_ack",
    "B>S:order, B>S:cancel_req, S>B:invoice, B>S:pay, S>L:delivery_req, L>B:deliver, B>S:confirm",
    "B>S:order, B>S:cancel_req, S>B:invoice, S>B:cancel_ack",
    "B>S:order, B>S:cancel_req, S>B:invoice, S>L:delivery_req, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, B>S:cancel_req, S>B:invoice, S>L:delivery_req, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, B>S:cancel_req, S>B:cancel_ack",
    "B>S:order, B>S:cancel_req, S>L:delivery_req, S>B:invoice, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, B>S:cancel_req, S>L:delivery_req, S>B:invoice, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, B>S:cancel_req, S>L:delivery_req, L>B:deliver, S>B:invoice, B>S:pay, B>S:confirm",
    "B>S:order, S>L:delivery_req, S>B:invoice, B>S:pay, B>S:cancel_req, L>B:deliver, B>S:confirm",
    "B>S:order, S>L:delivery_req, S>B:invoice, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, S>L:delivery_req, S>B:invoice, B>S:cancel_req, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, S>L:delivery_req, S>B:invoice, B>S:cancel_req, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, S>L:delivery_req, S>B:invoice, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, S>L:delivery_req, B>S:cancel_req, S>B:invoice, B>S:pay, L>B:deliver, B>S:confirm",
    "B>S:order, S>L:delivery_req, B>S:cancel_req, S>B:invoice, L>B:deliver, B>S:pay, B>S:confirm",
    "B>S:order, S>L:delivery_req, B>S:cancel_req, L>B:deliver, S>B:invoice, B>S:pay, B>S:confirm",
    "B>S:order, S>L:delivery_req, L>B:deliver, S>B:invoice, B>S:pay, B>S:confirm",
]

CANON_SET = {tuple(map(str.strip, s.split(","))) for s in CANON}

def load_sequences(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.sort_values(["id", "step"]).reset_index(drop=True)
    return df

def make_case_sequences(df: pd.DataFrame) -> pd.DataFrame:
    # Build sequences up to the first terminal (inclusive) if present
    terminal_set = {"B>S:confirm", "S>B:reject", "S>B:cancel_ack"}
    def truncate_to_terminal(codes: list[str]) -> list[str]:
        for i, c in enumerate(codes):
            if c in terminal_set:
                return codes[: i + 1]
        return codes

    seqs = (
        df.groupby("id")["code"].apply(list).reset_index(name="codes")
    )
    seqs["codes"] = seqs["codes"].apply(truncate_to_terminal)
    seqs["tuple"] = seqs["codes"].apply(tuple)
    return seqs

def classify(seqs: pd.DataFrame) -> pd.DataFrame:
    seqs["matched"] = seqs["tuple"].apply(lambda t: t in CANON_SET)
    return seqs

def terminals(df: pd.DataFrame) -> pd.DataFrame:
    last = df.sort_values(["id", "step"]).groupby("id").tail(1)
    last["terminal"] = last["code"].isin({"B>S:confirm", "S>B:reject", "S>B:cancel_ack"})
    return last[["id", "code", "terminal"]]

def main():
    if not SEQ_FILE.exists():
        print(f"❌ Sequence file not found: {SEQ_FILE}")
        return
    df = load_sequences(SEQ_FILE)

    # Parse timestamps to datetime (virtual-time aligned)
    df["timestamp_dt"] = pd.to_datetime(df["timestamp"], errors="coerce")
    tmin = df["timestamp_dt"].min()
    tmax = df["timestamp_dt"].max()
    if pd.notnull(tmin) and pd.notnull(tmax):
        half = tmin + (tmax - tmin) / 2
        print(f"⏱ Earliest virtual time: {tmin}")
        print(f"⏱ Latest virtual time:   {tmax}")
        print(f"⏱ Half-time threshold:   {half}")
    else:
        half = None
        print("⚠️ Could not parse timestamps; proceeding without half-time filter")

    # Filter to cases that started before half-time
    if half is not None:
        starts = df.groupby("id")["timestamp_dt"].min().rename("start_dt")
        start_ids = set(starts[starts < half].index)
        df_f = df[df["id"].isin(start_ids)].copy()
    else:
        df_f = df.copy()

    seqs = make_case_sequences(df_f)
    seqs = classify(seqs)
    term = terminals(df_f)

    # Report only terminal cases for matching coverage
    terminal_ids = set(term[term["terminal"]]["id"])
    seqs_term = seqs[seqs["id"].isin(terminal_ids)].copy()
    supported = int(seqs_term["matched"].sum())
    total = int(len(seqs_term))
    print(f"\n✅ Matched canonical sequences (terminal cases only): {supported}/{total}")

    # How many non-terminal cases in the filtered set
    nt = term[~term["terminal"]]
    print(f"Non-terminal cases in filtered set: {len(nt)}")

    # Breakdown of matched sequences
    matched = seqs_term[seqs_term["matched"]].copy()
    if not matched.empty:
        matched.loc[:, "seq_str"] = matched["tuple"].apply(lambda t: ", ".join(t))
        print("\nTop matched sequences:")
        print(matched["seq_str"].value_counts().head(20))

    # Variant diversity metrics (terminal cases only)
    if not seqs_term.empty:
        seqs_term = seqs_term.copy()
        seqs_term.loc[:, "seq_str"] = seqs_term["tuple"].apply(lambda t: ", ".join(t))
        distinct_total = seqs_term["seq_str"].nunique()
        distinct_matched = matched["seq_str"].nunique() if not matched.empty else 0
        distinct_unmatched = (
            seqs_term[~seqs_term["matched"]]["seq_str"].nunique()
            if ("matched" in seqs_term and (~seqs_term["matched"]).any()) else 0
        )
        print("\n📊 Variant diversity (terminal cases only):")
        print(f"Distinct executed variants: {distinct_total}")
        print(f"Distinct canonical variants matched: {distinct_matched}")
        print(f"Distinct non-canonical variants: {distinct_unmatched}")

        # List non-canonical variants with counts
        unmatched = seqs_term[~seqs_term["matched"]].copy()
        if not unmatched.empty:
            print("\n🧭 Non-canonical terminal variants (counts):")
            print(unmatched["seq_str"].value_counts())

    # List non-terminal cases for inspection
    if not nt.empty:
        print("\n⚠️ Non-terminal cases:")
        print(nt.to_string(index=False))
    else:
        print("\nAll filtered cases reached a terminal message.")

if __name__ == "__main__":
    main()
