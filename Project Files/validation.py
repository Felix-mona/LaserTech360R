"""
validation.py - Quality-assurance checks for the LaserTech 360R program.

Reads the raw disto and XPAD CSV files (before any processing) and reports
problems instead of crashing or silently dropping rows.

Two severity levels:
  ERROR   - the laser shot cannot be processed safely. It is added to
            report.bad_laser_ids so the main program can skip it.
  WARNING - the shot will still be processed, but a human should look at it.

Usage from Main.py:
    from validation import validate_inputs
    report = validate_inputs(args.disto, args.xpad)
    print(report.summary())

Usage stand-alone:
    python validation.py disto.csv xpad.csv
"""
import csv
import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# Settings - adjust these to suit your survey
# ---------------------------------------------------------------------------
LASER_CODE = "LZ"                      # XPAD code marking a laser set-up point
DATE_FORMAT = "%d/%m/%Y"               # e.g. 05/05/2026
TIME_FORMAT = "%H:%M:%S"               # e.g. 17:25:35

# Notes must look like:  <xpad id> t<3 digits> <genus>   e.g. "104 t034 willow"
NOTES_PATTERN = re.compile(
    r"^(?P<xpad_id>\S+)\s+(?P<code>t\d{3})\s+(?P<genus>[A-Za-z][A-Za-z\s\-]*)$"
)

# Genera/species seen so far (lower case). Anything else gets a WARNING so
# typos like "ahs" are caught. Add new ones here as you meet them.
# Set to an empty set() to switch this check off.
KNOWN_GENERA = {"ash", "fir", "willow", "beech","oak", "pine", "poplar", "spruce", "sycamore", "cedar", "elm", "larch", "maple", "birch", "hawthorn", "holly", "hazel", "rowan", "yew", "cherry", "alder", "cypress"}

MAX_HORIZ_DIST_M = 150.0               # warn above this (sample data peaks ~101 m)
MAX_ABS_VERT_DIST_M = 10.0             # warn if |vertical distance| exceeds this
SLOPE_TOLERANCE_M = 0.15               # allowed rounding gap in sqrt(h^2 + v^2) vs slope
MAX_TREE_DIAM_M = 2.0                  # warn above this diameter
MAX_GAP_AFTER_S = 600                  # warn if laser shot is >10 min after XPAD point
MAX_GAP_BEFORE_S = 60                  # warn if laser shot is >1 min BEFORE XPAD point
MAX_SITE_RADIUS_M = 1000.0             # warn if an XPAD point is this far from the median

DISTO_REQUIRED = ["Measurement #", "Horizontal Distance (m)", "Azimuth (deg)",
                  "Date", "Time", "Notes"]
XPAD_REQUIRED = ["Name", "Code", "Point East/E", "Point North/N",
                 "Date start (local)", "Time start (local)"]


# ---------------------------------------------------------------------------
# Report objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Issue:
    severity: str    # "ERROR" or "WARNING"
    source: str      # "DISTO", "XPAD", "CROSS" (between the two files) or "FILE"
    ref: str         # where to look, e.g. "Disto line 9 (Measurement #9)"
    message: str


class ValidationReport:
    def __init__(self):
        self.issues = []
        self.bad_laser_ids = set()     # Measurement # values that must be skipped
        self.fatal = False             # True if a file was unreadable / wrong format
        self.n_disto_rows = 0
        self.n_disto_excluded = 0
        self.n_xpad_laser_rows = 0
        self.n_errors = 0
        self.n_warnings = 0

    def add(self, severity, source, ref, message):
        self.issues.append(Issue(severity, source, ref, message))
        if severity == "ERROR":
            self.n_errors += 1
        else:
            self.n_warnings += 1

    def _sorted_issues(self):
        # Errors first; sort is stable so original order is kept within a group
        return sorted(self.issues, key=lambda i: i.severity != "ERROR")

    def summary(self):
        lines = []
        if self.fatal:
            lines.append("Validation could not run - fix the file problem(s) below.")
        else:
            lines.append(f"Disto rows read: {self.n_disto_rows}   "
                         f"XPAD laser points: {self.n_xpad_laser_rows}")
            lines.append(f"Disto rows that will be processed: "
                         f"{self.n_disto_rows - self.n_disto_excluded}   "
                         f"excluded: {self.n_disto_excluded}")
        lines.append(f"{self.n_errors} error(s), {self.n_warnings} warning(s)")
        for issue in self._sorted_issues():
            lines.append(f"  [{issue.severity}] {issue.ref}: {issue.message}")
        return "\n".join(lines)

    def write_csv(self, path):
        """Write the issues to a CSV that opens cleanly in Excel."""
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Severity", "Source", "Reference", "Message"])
            for i in self._sorted_issues():
                writer.writerow([i.severity, i.source, i.ref, i.message])


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _get(row, column):
    """Return a stripped string for a cell, '' if missing."""
    return (row.get(column) or "").strip()


def _to_float(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _to_datetime(date_text, time_text):
    try:
        return datetime.strptime(f"{date_text} {time_text}",
                                 f"{DATE_FORMAT} {TIME_FORMAT}")
    except ValueError:
        return None


def _read_rows(path, required_columns, source, report):
    """Read a CSV into a list of (line_number, row_dict). Flags fatal problems."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            missing = [c for c in required_columns if c not in (reader.fieldnames or [])]
            if missing:
                report.add("ERROR", "FILE", f"{source} file",
                           f"Missing column(s): {', '.join(missing)}. Is this the right file?")
                report.fatal = True
                return []
            rows = [(reader.line_num, row) for row in reader]
    except (OSError, UnicodeDecodeError) as exc:
        report.add("ERROR", "FILE", f"{source} file", f"Could not read '{path}': {exc}")
        report.fatal = True
        return []

    if not rows:
        report.add("ERROR", "FILE", f"{source} file", "File contains no data rows")
        report.fatal = True
    return rows


def _diagnose_notes(notes):
    """Explain *why* a notes field doesn't match the expected format."""
    parts = notes.split()
    if not parts:
        return "Notes are empty (expected e.g. '104 t034 ash')"
    if len(parts) < 3:
        return (f"Notes '{notes}' have {len(parts)} item(s); expected 3: "
                f"XPAD ID, tree code, genus (e.g. '104 t034 ash')")
    if not re.fullmatch(r"t\d{3}", parts[1]):
        return (f"Tree code '{parts[1]}' should be a lowercase 't' followed by "
                f"3 digits (e.g. t034)")
    return f"Genus '{' '.join(parts[2:])}' should contain letters only"


# ---------------------------------------------------------------------------
# Disto checks (one row at a time)
# ---------------------------------------------------------------------------
def _check_disto(rows, report):
    info = []
    seen_ids = set()

    for line, row in rows:
        mid = _get(row, "Measurement #")
        ref = f"Disto line {line} (Measurement #{mid or '?'})"
        errors_before = report.n_errors

        # Measurement number: needed for the Joint Pt ID, so must be unique
        if not mid:
            report.add("ERROR", "DISTO", ref, "Measurement # is missing")
        elif mid in seen_ids:
            report.add("ERROR", "DISTO", ref,
                       "Duplicate Measurement # (all rows with this number are skipped)")
        seen_ids.add(mid)

        # Horizontal distance
        horiz = _to_float(_get(row, "Horizontal Distance (m)"))
        if horiz is None:
            report.add("ERROR", "DISTO", ref, "Horizontal distance is missing or not a number")
        elif horiz <= 0:
            report.add("ERROR", "DISTO", ref, f"Horizontal distance {horiz} m must be greater than 0")
        elif horiz > MAX_HORIZ_DIST_M:
            report.add("WARNING", "DISTO", ref,
                       f"Horizontal distance {horiz} m is unusually long (limit {MAX_HORIZ_DIST_M} m)")

        # Azimuth
        azimuth = _to_float(_get(row, "Azimuth (deg)"))
        if azimuth is None:
            report.add("ERROR", "DISTO", ref, "Azimuth is missing or not a number")
        elif not 0 <= azimuth <= 360:
            report.add("ERROR", "DISTO", ref, f"Azimuth {azimuth} is outside 0-360 degrees")

        # Vertical distance (optional column, not yet used for height)
        vert_text = _get(row, "Vertical Distance (m)")
        vert = _to_float(vert_text)
        if vert_text and vert is None:
            report.add("WARNING", "DISTO", ref, "Vertical distance is not a number")
        elif vert is not None and abs(vert) > MAX_ABS_VERT_DIST_M:
            report.add("WARNING", "DISTO", ref,
                       f"Vertical distance {vert} m is unusually large")

        # Internal consistency: horizontal and vertical should reproduce slope distance
        slope = _to_float(_get(row, "Slope Distance (m)"))
        if None not in (horiz, vert, slope):
            expected = math.hypot(horiz, vert)
            if abs(expected - slope) > SLOPE_TOLERANCE_M:
                report.add("WARNING", "DISTO", ref,
                           f"Slope distance {slope} m doesn't match horizontal/vertical "
                           f"(expected about {expected:.2f} m)")

        # Notes: XPAD ID, tree code, genus
        notes = _get(row, "Notes")
        match = NOTES_PATTERN.match(notes)
        xpad_id = None
        if not match:
            report.add("ERROR", "DISTO", ref, _diagnose_notes(notes))
        else:
            xpad_id = match["xpad_id"]
            code = match["code"]
            genus = " ".join(match["genus"].split())
            diameter = int(code[1:3]) / 10        # t034 -> 03 -> 0.3 m
            if diameter == 0:
                report.add("ERROR", "DISTO", ref, f"Tree code {code} gives a diameter of 0 m")
            elif diameter > MAX_TREE_DIAM_M:
                report.add("WARNING", "DISTO", ref,
                           f"Tree code {code} gives a diameter of {diameter} m - is that right?")
            if KNOWN_GENERA and genus.lower() not in KNOWN_GENERA:
                report.add("WARNING", "DISTO", ref,
                           f"Genus '{genus}' is not in the known list - check spelling")

        # Date / time (used for the cross-file timing check)
        when = _to_datetime(_get(row, "Date"), _get(row, "Time"))
        if when is None:
            report.add("WARNING", "DISTO", ref,
                       "Date/time not in expected format (DD/MM/YYYY HH:MM:SS) - timing check skipped")

        if report.n_errors > errors_before:
            report.bad_laser_ids.add(mid)
        info.append({"mid": mid, "ref": ref, "xpad_id": xpad_id, "when": when})

    return info


# ---------------------------------------------------------------------------
# XPAD checks
# ---------------------------------------------------------------------------
def _check_xpad(rows, report):
    by_name = {}          # name -> first laser row with that name
    unusable = {}         # name -> reason the point can't be used
    codes_by_name = {}    # name -> set of codes seen (for better error messages)

    for line, row in rows:
        name = _get(row, "Name")
        code = _get(row, "Code")
        codes_by_name.setdefault(name, set()).add(code)
        if code != LASER_CODE:
            continue                       # control points etc. are ignored

        report.n_xpad_laser_rows += 1
        ref = f"XPAD line {line} (Name {name or '?'})"

        if not name:
            report.add("ERROR", "XPAD", ref, "Laser point has no Name")
            continue

        east = _to_float(_get(row, "Point East/E"))
        north = _to_float(_get(row, "Point North/N"))
        coords_ok = east is not None and north is not None and east != 0 and north != 0
        if not coords_ok:
            report.add("ERROR", "XPAD", ref,
                       "Easting/Northing missing, not a number, or 0 (no GNSS fix?)")


        when = _to_datetime(_get(row, "Date start (local)"), _get(row, "Time start (local)"))
        if when is None:
            report.add("WARNING", "XPAD", ref,
                       "Date/time not in expected format - timing check skipped")

        if name in by_name:
            report.add("ERROR", "XPAD", ref,
                       "Duplicate laser point name (disto rows using it are skipped)")
            unusable[name] = "the name appears more than once in the XPAD file"
            continue

        by_name[name] = {"ref": ref, "east": east, "north": north, "when": when}
        if not coords_ok:
            unusable[name] = "its coordinates are invalid"

    # Typo check: flag points far away from the rest of the site
    good = [(n, p) for n, p in by_name.items() if n not in unusable]
    if len(good) >= 3:
        med_e = statistics.median(p["east"] for _, p in good)
        med_n = statistics.median(p["north"] for _, p in good)
        for name, point in good:
            distance = math.hypot(point["east"] - med_e, point["north"] - med_n)
            if distance > MAX_SITE_RADIUS_M:
                report.add("WARNING", "XPAD", point["ref"],
                           f"Point is {distance:.0f} m from the middle of the site - typo in coordinates?")

    return by_name, unusable, codes_by_name


# ---------------------------------------------------------------------------
# Checks that compare the two files
# ---------------------------------------------------------------------------
def _cross_check(disto_info, by_name, unusable, codes_by_name, report):
    referenced = set()

    for d in disto_info:
        xid = d["xpad_id"]
        if xid is None:
            continue                       # notes already failed
        referenced.add(xid)

        if xid in unusable:
            report.add("ERROR", "CROSS", d["ref"],
                       f"XPAD point '{xid}' cannot be used: {unusable[xid]}")
            report.bad_laser_ids.add(d["mid"])
            continue

        point = by_name.get(xid)
        if point is None:
            if xid in codes_by_name:
                codes = ", ".join(sorted(c or "blank" for c in codes_by_name[xid]))
                message = f"XPAD point '{xid}' exists but its Code is '{codes}', not '{LASER_CODE}'"
            else:
                message = f"XPAD point '{xid}' was not found in the XPAD file"
            report.add("ERROR", "CROSS", d["ref"], message)
            report.bad_laser_ids.add(d["mid"])
            continue

        # Laser shot should be taken shortly after the XPAD point was logged
        if d["when"] and point["when"]:
            gap = (d["when"] - point["when"]).total_seconds()
            if gap > MAX_GAP_AFTER_S:
                report.add("WARNING", "CROSS", d["ref"],
                           f"Shot was {gap / 60:.1f} min after XPAD point '{xid}' - "
                           f"check the XPAD ID in the notes")
            elif gap < -MAX_GAP_BEFORE_S:
                report.add("WARNING", "CROSS", d["ref"],
                           f"Shot was {abs(gap):.0f} s BEFORE XPAD point '{xid}' was logged - "
                           f"check the XPAD ID in the notes")

    for name, point in by_name.items():
        if name not in referenced:
            report.add("WARNING", "XPAD", point["ref"],
                       "Laser point is not used by any shot in the disto file")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def validate_inputs(disto_file, xpad_file):
    """Run every check and return a ValidationReport."""
    report = ValidationReport()

    disto_rows = _read_rows(disto_file, DISTO_REQUIRED, "DISTO", report)
    xpad_rows = _read_rows(xpad_file, XPAD_REQUIRED, "XPAD", report)
    if report.fatal:
        return report

    disto_info = _check_disto(disto_rows, report)
    by_name, unusable, codes_by_name = _check_xpad(xpad_rows, report)
    _cross_check(disto_info, by_name, unusable, codes_by_name, report)

    report.n_disto_rows = len(disto_info)
    report.n_disto_excluded = sum(1 for d in disto_info if d["mid"] in report.bad_laser_ids)
    return report


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python validation.py <disto_csv> <xpad_csv>")
        sys.exit(2)
    result = validate_inputs(sys.argv[1], sys.argv[2])
    print(result.summary())
    sys.exit(1 if result.n_errors else 0)
