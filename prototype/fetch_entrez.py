#!/usr/bin/env python3
"""
Fetch FULL-TEXT / abstract XML from NCBI Entrez for the HSPB1 use case.

Run this in an environment with outbound access to eutils.ncbi.nlm.nih.gov
(e.g. your Vertex/GCP notebook). It is NOT runnable inside the sandboxed agent
container, where NCBI egress is blocked -- that is why the repo also ships a
synthetic fixture (sample/hspb1_pubmed_sample.xml) so the demos run offline.

The user asked for FULL XML (not abstracts) because the fidelity analysis needs
detail. For full text prefer PMC (efetch db=pmc, rettype=full); PubMed (db=pubmed)
returns abstracts + metadata only.

Usage:
  python3 fetch_entrez.py --email you@example.com --pmcids PMC1234567 PMC7654321
  python3 fetch_entrez.py --email you@example.com --pmids 22176143 21611841 --db pubmed

Writes one XML file per id into sample/entrez/.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample", "entrez")


def fetch(db: str, uid: str, email: str, api_key: str | None) -> bytes:
    params = {
        "db": db,
        "id": uid,
        "retmode": "xml",
        "email": email,
        "tool": "genephen-fidelity-eval",
    }
    if db == "pmc":
        params["rettype"] = "full"
    if api_key:
        params["api_key"] = api_key
    url = EUTILS + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True, help="NCBI requires a contact email")
    ap.add_argument("--db", default="pmc", choices=["pmc", "pubmed"],
                    help="pmc = full text (preferred); pubmed = abstract only")
    ap.add_argument("--pmcids", nargs="*", default=[])
    ap.add_argument("--pmids", nargs="*", default=[])
    ap.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY"))
    args = ap.parse_args()

    ids = args.pmcids if args.db == "pmc" else args.pmids
    ids = ids or (args.pmcids + args.pmids)
    if not ids:
        print("Provide --pmcids (for db=pmc) or --pmids (for db=pubmed).", file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    delay = 0.11 if args.api_key else 0.34  # respect NCBI rate limits (10/s vs 3/s)
    for uid in ids:
        try:
            data = fetch(args.db, uid, args.email, args.api_key)
            path = os.path.join(OUT_DIR, f"{uid}.xml")
            with open(path, "wb") as f:
                f.write(data)
            print(f"saved {path} ({len(data)} bytes)")
        except Exception as e:  # noqa: BLE001
            print(f"FAILED {uid}: {e}", file=sys.stderr)
        time.sleep(delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
