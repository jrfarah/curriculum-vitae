#!/usr/bin/env python3
"""
Generate a LaTeX-formatted, numbered publications list from a .bib file.

Rules:
- Two sections: First-author and Normal contribution.
- First-author entries:
    * Begin authors with \textbf{J. R. Farah}, then co-authors:
        - total authors > 5 → include up to the 3rd author
        - total authors ≤ 5 → include up to the 5th author
    * If there are more authors than shown, append ", \\textit{et al.}." to the authors block; else end with a period.
- Normal contribution entries:
    * If first author is a collaboration (e.g., "... Collaboration"):
        - Output that collaboration name, then ", ..., ", then \textbf{J. R. Farah}.
        - If there are other authors beyond Farah, append ", \\textit{et al.}." (after Farah). Otherwise end with a period.
    * Otherwise:
        - If Farah index ≤ 2: output up to the first 3 authors (bold Farah in place). If there are more authors than shown, append ", \\textit{et al.}." at the end (this appears after Farah). Else end with a period.
        - If Farah index ≥ 3: output first 3 authors, then ", ..., ", then \textbf{J. R. Farah}. If there are authors after Farah, append ", \\textit{et al.}." after Farah. Else end with a period.
- Then: YEAR., \\textit{Title}., Journal, volume, pages/eid., optional arXiv link.
- Numbering per section: oldest = 1 at bottom; newest at top with the largest number.
- .bib may be unordered and may wrap names with braces {}. Braces are stripped for matching/formatting.

Usage:
  python make_publist.py path/to/file.bib > pubs.tex
"""

import sys
import re
import datetime
from pathlib import Path

# --------- Configuration ----------
TARGET_SURNAME = "Farah"
TARGET_BOLD_TEXT = r"J. R. Farah"
TARGET_BOLD = r"\textbf{" + TARGET_BOLD_TEXT + r"}"
TARGET_GIVEN_VARIANTS = {"Joseph", "J.", "J", "Joseph R.", "J. R.", "Joseph R"}
GROUP_KEYWORDS = {"collaboration", "consortium"}
# ----------------------------------

# ---------------- BibTeX parsing (brace-aware) ----------------

def _read_balanced_braces(s, i):
    assert s[i] == "{"
    depth = 0
    start = i + 1
    i += 1
    while i < len(s):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return s[start:i], i + 1
            depth -= 1
        i += 1
    return s[start:], i

def _read_quoted(s, i):
    assert s[i] == '"'
    i += 1
    out = []
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append(s[i + 1])
            i += 2
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    return "".join(out), i

def _skip_ws_commas(s, i):
    while i < len(s) and s[i] in " \t\r\n,":
        i += 1
    return i

def _read_identifier(s, i):
    start = i
    while i < len(s) and re.match(r"[A-Za-z0-9_\-]", s[i]):
        i += 1
    return s[start:i], i

def _parse_fields(body):
    i = 0
    n = len(body)
    fields = {}
    while True:
        i = _skip_ws_commas(body, i)
        if i >= n:
            break
        key, i2 = _read_identifier(body, i)
        if not key:
            break
        i = _skip_ws_commas(body, i2)
        if i >= n or body[i] != "=":
            break
        i += 1
        i = _skip_ws_commas(body, i)
        if i >= n:
            break
        if body[i] == "{":
            val, i = _read_balanced_braces(body, i)
        elif body[i] == '"':
            val, i = _read_quoted(body, i)
        else:
            start = i
            while i < n and body[i] not in ",\n\r":
                i += 1
            val = body[start:i].strip()
        fields[key.lower()] = " ".join(val.split())
        i = _skip_ws_commas(body, i)
    return fields

def load_bib(path):
    s = Path(path).read_text(encoding="utf-8", errors="ignore")
    i = 0
    entries = []
    while True:
        at = s.find("@", i)
        if at == -1:
            break
        m = re.match(r"@([A-Za-z]+)\s*\{", s[at:])
        if not m:
            i = at + 1
            continue
        kind = m.group(1).lower()
        j = at + m.end()  # points at '{'
        depth = 1
        start_inside = j
        while j < len(s) and depth > 0:
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
            j += 1
        entry_block = s[start_inside:j-1]
        key_end = entry_block.find(",")
        if key_end == -1:
            i = j
            continue
        key = entry_block[:key_end].strip()
        fields_body = entry_block[key_end+1:].strip().rstrip(",")
        fields = _parse_fields(fields_body)
        entries.append({"kind": kind, "key": key, **fields})
        i = j
    return entries

# ---------------- Utilities ----------------

def strip_braces(x: str) -> str:
    return x.replace("{", "").replace("}", "").strip()

def normalize_whitespace(x: str) -> str:
    return " ".join(x.split())

def normalize_initials(first: str) -> str:
    if not first:
        return ""
    toks = [t for t in re.split(r"[\s\-]+", first) if t]
    out = []
    for t in toks:
        t = strip_braces(t).strip(".")
        if not t:
            continue
        out.append(f"{t[0]}." )
    return " ".join(out)

# ---------------- Author handling ----------------

def split_authors(author_field):
    parts = [normalize_whitespace(p) for p in re.split(r"\s+and\s+", author_field)]
    out = []
    for a in parts:
        raw = strip_braces(a)
        # Group author?
        if ("," not in raw) and any(k in raw.lower() for k in GROUP_KEYWORDS):
            out.append({"group": raw})
            continue
        if "," in raw:
            last, first = [normalize_whitespace(strip_braces(t)) for t in raw.split(",", 1)]
        else:
            toks = raw.split()
            last = toks[-1].strip()
            first = " ".join(toks[:-1]).strip()
        out.append({"first": first, "last": last, "raw": raw})
    return out

def is_group_author(name_dict):
    return "group" in name_dict and bool(name_dict["group"].strip())

def render_name(name_dict, bold_if_target=False):
    if is_group_author(name_dict):
        return name_dict["group"]
    last = name_dict.get("last","").strip()
    first = name_dict.get("first","").strip()
    if not last and name_dict.get("raw"):
        return name_dict["raw"]
    ini = normalize_initials(first)
    text = f"{last}, {ini}" if ini else last
    if bold_if_target and is_target_author(name_dict):
        return TARGET_BOLD
    return text

def is_target_author(name_dict):
    if is_group_author(name_dict):
        return False
    last_ok = strip_braces(name_dict.get("last","")).lower() == TARGET_SURNAME.lower()
    if not last_ok:
        return False
    f = strip_braces(name_dict.get("first","")).replace(",", " ").strip()
    if not f:
        return True
    toks = [t.strip(".") for t in f.split()]
    variants = {t+"." if len(t)==1 else t for t in toks} | {" ".join(toks)}
    v1 = {v for v in variants}
    v2 = {v.replace(".","") for v in variants}
    t1 = set(TARGET_GIVEN_VARIANTS)
    t2 = {w.replace(".","") for w in TARGET_GIVEN_VARIANTS}
    return bool(v1 & t1) or bool(v2 & t2)

def find_target_index(authors):
    for i, a in enumerate(authors):
        if is_target_author(a):
            return i
    return -1

# ---------------- Date, journal, arXiv ----------------

def pick_year_month_day(ent):
    y = None
    if "year" in ent:
        m = re.search(r"\d{4}", ent["year"])
        if m:
            y = int(m.group(0))
    if y is None and "date" in ent:
        m = re.search(r"(\d{4})", ent["date"])
        if m:
            y = int(m.group(1))
    mth, day = 12, 31
    if "month" in ent:
        mm = ent["month"].strip().lower()
        mdigits = re.search(r"\d{1,2}", mm)
        if mdigits:
            mth = max(1, min(12, int(mdigits.group(0))))
        else:
            abbr = mm[:3]
            map3 = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            if abbr in map3:
                mth = map3[abbr]
    if "date" in ent:
        m2 = re.search(r"^\s*\d{4}-(\d{2})", ent["date"])
        d2 = re.search(r"^\s*\d{4}-\d{2}-(\d{2})", ent["date"])
        if m2:
            mth = int(m2.group(1))
        if d2:
            day = int(d2.group(1))
    if y is None:
        y, mth, day = 0, 1, 1
    try:
        return datetime.date(y, mth, day)
    except Exception:
        return datetime.date(y if y else 0, 1, 1)

def format_year(ent):
    y = None
    if "year" in ent:
        m = re.search(r"\d{4}", ent["year"])
        if m:
            y = m.group(0)
    if y is None and "date" in ent:
        m = re.search(r"\d{4}", ent["date"])
        if m:
            y = m.group(0)
    return f"{y}." if y else ""

def sanitize_title_text(t: str) -> str:
    # Fix brace-wrapped macros missing backslash
    t = re.sub(r"\{(texten|textem)dash\}", lambda m: "\\" + m.group(1) + "dash", t)
    # Fix bare tokens missing backslash
    t = re.sub(r"(?<!\\)\b(textendash|textemdash)\b", r"\\\1", t)
    # Normalize Unicode dashes to TeX-safe ASCII
    t = t.replace("–", "--").replace("—", "---")
    return t

def format_title(ent):
    t = ent.get("title","").strip()
    if t.startswith("{") and t.endswith("}"):
        t = t[1:-1]
    t = sanitize_title_text(t)
    return r"\textit{" + t + "}."


def format_journal_block(ent):
    journal = ent.get("journal","").strip()
    volume = ent.get("volume","").strip()
    pages  = ent.get("pages","").strip() or ent.get("eid","").strip()

    if journal.lower().startswith("arxiv"):
        return "arXiv e-prints,"  # comma; hyperlink follows

    parts = []
    if journal: parts.append(journal)
    if volume:  parts.append(volume)
    if pages:   parts.append(pages)
    if not parts: return ""
    return (f"{parts[0]}." if len(parts)==1 else f"{parts[0]}, " + ", ".join(parts[1:]) + ".")


def format_arxiv(ent):
    eprint = ent.get("eprint","").strip()
    ap = ent.get("archiveprefix","").strip().lower()
    url = ent.get("url","").strip()
    if (eprint and ap == "arxiv") or (eprint and re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", eprint)):
        link = f"https://arxiv.org/abs/{eprint}"
        return r"\href{" + link + "}{" + f"arXiv:{eprint}" + "}"
    if "arxivid" in ent and ent["arxivid"].strip():
        arx = ent["arxivid"].strip()
        link = f"https://arxiv.org/abs/{arx}"
        return r"\href{" + link + "}{" + f"arXiv:{arx}" + "}"
    if url and "arxiv.org" in url:
        m = re.search(r"arxiv\.org/(abs|pdf)/([0-9]{4}\.[0-9]{4,5}(v\d+)?)", url)
        if m:
            arx = m.group(2)
            link = f"https://arxiv.org/abs/{arx}"
            return r"\href{" + link + "}{" + f"arXiv:{arx}" + "}"
    return ""

# ---------------- Author list formatting per section ----------------

def ensure_trailing_period(s: str) -> str:
    s = s.rstrip()
    return s if s.endswith(".") else s + "."

def format_authors_first_author(authors):
    n = len(authors)
    cutoff = 3 if n > 5 else 5
    shown = authors[:cutoff]
    parts = [TARGET_BOLD]
    for a in shown[1:]:
        parts.append(render_name(a))
    author_str = ", ".join(parts)
    if n > cutoff:
        author_str += ", \\textit{et al.}."
    else:
        author_str = ensure_trailing_period(author_str)
    return author_str

def is_collaboration_author(name_dict):
    if is_group_author(name_dict):
        txt = name_dict["group"].lower()
        return any(k in txt for k in GROUP_KEYWORDS)
    last = strip_braces(name_dict.get("last","")).lower()
    raw = strip_braces(name_dict.get("raw","")).lower()
    return any(k in last for k in GROUP_KEYWORDS) or any(k in raw for k in GROUP_KEYWORDS)

def format_authors_normal(authors):
    if not authors:
        return "."
    n = len(authors)

    if is_collaboration_author(authors[0]):
        lead = render_name(authors[0])
        fi = find_target_index(authors)
        s = f"{lead}, ..., {TARGET_BOLD}"
        if (fi >= 0 and fi < n - 1) or (fi == -1 and n > 1):
            s += ", \\textit{et al.}."
        else:
            s = ensure_trailing_period(s)
        return s

    fi = find_target_index(authors)
    first_three = [render_name(a, bold_if_target=True) for a in authors[:3]]

    if 0 <= fi <= 2:
        s = ", ".join(first_three)
        if n > len(first_three):
            s += ", \\textit{et al.}."
        else:
            s = ensure_trailing_period(s)
        return s

    if fi >= 0:
        s = ", ".join(first_three + ["...", TARGET_BOLD])
        if fi < n - 1:
            s += ", \\textit{et al.}."
        else:
            s = ensure_trailing_period(s)
        return s

    s = ", ".join(first_three)
    if n > len(first_three):
        s += ", \\textit{et al.}."
    else:
        s = ensure_trailing_period(s)
    return s


# ---------------- Build entries ----------------

def build_entry_line(ent, idx, section):
    authors_field = ent.get("author","").strip()
    authors = split_authors(authors_field) if authors_field else []
    if section == "first":
        authors_str = format_authors_first_author(authors)
    else:
        authors_str = format_authors_normal(authors)
    year_str = format_year(ent)
    title_str = format_title(ent)
    journal_str = format_journal_block(ent)
    arxiv_str = format_arxiv(ent)
    blocks = [authors_str, year_str, title_str]
    if journal_str:
        blocks.append(journal_str)
    if arxiv_str:
        blocks.append(arxiv_str + ".")
    return f"{idx}. " + " ".join(b for b in blocks if b)

# ---------------- Main ----------------

def is_first_author_entry(ent):
    if "author" not in ent:
        return False
    authors = split_authors(ent["author"])
    return len(authors) > 0 and is_target_author(authors[0])

def main():
    if len(sys.argv) < 2:
        print("Usage: python make_publist.py path/to/file.bib", file=sys.stderr)
        sys.exit(1)

    entries = load_bib(sys.argv[1])
    entries = [e for e in entries if e.get("author") and e.get("title")]

    for e in entries:
        e["_date"] = pick_year_month_day(e)

    first_author_entries = [e for e in entries if is_first_author_entry(e)]
    normal_entries = [e for e in entries if e not in first_author_entries]

    first_author_entries.sort(key=lambda x: (x["_date"], x.get("year",""), x.get("title","")))
    normal_entries.sort(key=lambda x: (x["_date"], x.get("year",""), x.get("title","")))

    for i, e in enumerate(first_author_entries, start=1):
        e["_num"] = i
    for i, e in enumerate(normal_entries, start=1):
        e["_num"] = i

    first_author_entries_display = list(reversed(first_author_entries))
    normal_entries_display = list(reversed(normal_entries))

    out = []
    out.append(r"% ---- AUTO-GENERATED PUBLICATIONS LIST ----")
    out.append(r"% Requires \usepackage{hyperref}")
    out.append(r"\section*{First-author}")
    if first_author_entries_display:
        for e in first_author_entries_display:
            out.append(build_entry_line(e, e["_num"], section="first"))
    else:
        out.append(r"(none)")
    out.append("")
    out.append(r"\section*{Normal contribution}")
    if normal_entries_display:
        for e in normal_entries_display:
            out.append(build_entry_line(e, e["_num"], section="normal"))
    else:
        out.append(r"(none)")

    print("\n\n".join(out))

if __name__ == "__main__":
    main()
