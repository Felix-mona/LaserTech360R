import argparse
import os
import sys
import traceback

import Data_manipulation as DM
from validation import validate_inputs

REPORT_NAME = "validation_report.csv"   # written next to the output file; Excel reads it


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--disto", required=True)
    p.add_argument("--xpad", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, REPORT_NAME)

    # 1. Validate FIRST, so bad data is reported instead of crashing the run
    report = validate_inputs(args.disto, args.xpad)
    report.write_csv(report_path)
    print(report.summary())
    if report.fatal:
        return 2   # unreadable file or wrong columns - nothing can be processed

    # 2. Process only the rows that passed validation
    try:
        disto_data = DM.reduce_disto_output(args.disto, skip_ids=report.bad_laser_ids)
        xpad_data = DM.reduce_xpad_output(args.xpad)
        new_coordinates = DM.calculate_new_coordinates(disto_data, xpad_data)
        DM.write_to_ktf_format(args.out, new_coordinates)
    except Exception as exc:
        # e.g. the output file is open in another program
        traceback.print_exc()
        report.add("ERROR", "PROGRAM", "Main.py", f"Unexpected error: {exc!r}")
        report.write_csv(report_path)
        return 1

    print(f"Wrote {len(new_coordinates)} of {report.n_disto_rows} laser shots to {args.out}")
    return 0   # 0 = output written (some rows may still be flagged in the report)


if __name__ == "__main__":
    sys.exit(main())
