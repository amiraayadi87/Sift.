"""Stitch JobRadar's location / agency / text helpers and the collector into one file: fewer_feed.py"""
import re
from pathlib import Path

ROOT = Path(__file__).parent
JR = ROOT


def strip(src: str) -> str:
    src = re.sub(r'^""".*?"""\n', "", src, count=1, flags=re.S)
    src = re.sub(r"^from __future__ import annotations\n", "", src, flags=re.M)
    src = re.sub(r"^from \.+[\w.]* import .*\n", "", src, flags=re.M)
    return src


def section(path: Path, names=None) -> str:
    src = strip(path.read_text())
    if not names:
        return src
    # keep only the named top-level defs/assignments
    out, keep = [], False
    for line in src.splitlines(keepends=True):
        if re.match(r"^(def|class|[A-Z_]+\s*=|_[A-Z_]+\s*=)", line):
            name = re.match(r"^(?:def|class)?\s*(\w+)", line).group(1)
            keep = name in names
        elif re.match(r"^\S", line) and not line.startswith((")", "]", "}")):
            keep = keep and line.startswith(("#",)) is False and False
        if keep:
            out.append(line)
    return "".join(out)


header = '''#!/usr/bin/env python3
"""Fewer daily feed collector (single file, standard library only).
Built from JobRadar (location, agency and text helpers) + the collector. Do not edit by hand:
regenerate with make_single_file.py."""
import hashlib
import html as _html
import re
import unicodedata
'''

parts = [
    header,
    "\n# ---------------------------------------------------------------- location (from JobRadar geo.py)\n",
    strip((JR / "geo.py").read_text()).replace("import re\nimport unicodedata\n", ""),
    "\n# ---------------------------------------------------------------- text helpers (from JobRadar models.py)\n",
    section(JR / "models.py", {"_COMPANY_SUFFIX", "_TITLE_NOISE", "norm_company", "norm_title", "_TAGS", "html_to_text"}),
    "\n# ---------------------------------------------------------------- agencies (from JobRadar dedupe.py)\n",
    section(JR / "dedupe.py", {"AGENCY_WORDS", "KNOWN_AGENCIES", "looks_like_agency"}),
    "\n",
    (ROOT / "collector_core.py").read_text(),
    "\n",
    (ROOT / "na_core.py").read_text(),
    '''

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("na-"):
        sys.exit(na_main(sys.argv[1:]))
    sys.exit(main())
''',
]
out = "".join(parts)
out = out.replace("    import html as _html\n", "")
(ROOT.parent / "na_engine.py").write_text(out)
print(f"wrote fewer_feed.py ({len(out.splitlines())} lines)")
