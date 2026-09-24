#!/usr/bin/env python3
"""Recover March 2026 FedWatch observations from SinoPac's public PDF archive.

One-off historical import; requires pdfplumber in the analysis environment.
Preserves each PDF and its hash. Only numerical facts are extracted. Run the
normal collector with --offline afterwards. Report dates get the same
conservative end-of-day availability bound as daily CME exports, so these
are explicitly labelled archival observations, not CME closing prices.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys

import pdfplumber
import requests

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'https://www.spf.com.tw/sinopacSPF/research/list.do?id=18d5d32463100000a0821ca2135dcd5d'


def extract(path, report_date):
    with pdfplumber.open(path) as pdf:
        page = next(p for p in pdf.pages if '2026/03/18' in (p.extract_text() or '')
                    and '2026/04/29' in (p.extract_text() or ''))
        text = page.extract_text()
        date = datetime.strptime(report_date, '%Y/%m/%d')
        if not re.search(rf'{date.year}年\s*{date.month}月\s*{date.day}日', text):
            raise ValueError(f'Report and table dates disagree: {path}')
        words = page.extract_words()
        row = next(w for w in words if w['text'] == '2026/03/18')
        headers = [w for w in words if w['top'] < row['top'] and re.fullmatch(r'\d+\.\d{2}', w['text'])]
        top = min(w['top'] for w in headers)
        lowers = sorted([w for w in headers if abs(w['top']-top) < 2], key=lambda w:w['x0'])
        columns = []
        def center(w):
            return (w['x0']+w['x1'])/2
        for lower in lowers:
            upper = next(w for w in headers if w['top'] > lower['bottom'] and abs(center(w)-center(lower)) < 3)
            lo, hi = round(float(lower['text'])*100), round(float(upper['text'])*100)
            if hi-lo != 25:
                raise ValueError('Unexpected target range')
            columns.append((center(lower), f'({lo}-{hi})'))
        values = {label: 0.0 for _,label in columns}
        used = set()
        for w in words:
            if abs(w['top']-row['top']) < 2 and w is not row:
                value = float(w['text'])/100
                x, label = min(columns, key=lambda c:abs(c[0]-center(w)))
                if abs(x-center(w)) > 12 or label in used or not 0 <= value <= 1:
                    raise ValueError('Ambiguous probability cell')
                values[label] = value
                used.add(label)
        if abs(sum(values.values())-1) > .001:
            raise ValueError('Incomplete probability distribution')
        reported = re.search(r'數據時間\s*(\d{4}年\s*\d+月\s*\d+日\s*\d{2}:\d{2})', text)
        if not reported:
            raise ValueError('Missing table observation time')
        return values, reported[1]


def main():
    raw = Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'data/fed_comparison/raw'
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = raw/'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    response = requests.get(INDEX, timeout=30)
    response.raise_for_status()
    index = response.text
    reports = re.findall(r'<a href="(/upload/sinopac/researchContent/[^" ]+\.pdf)"[^>]*>.*?</a>\s*<span>(2026/\d\d/\d\d)</span>', index, re.S)
    rows, inputs = [], []
    now = datetime.now(timezone.utc).isoformat()
    for relative, date in sorted(reports, key=lambda r:r[1]):
        if not '2026/02/11' <= date <= '2026/03/17':
            continue
        url = 'https://www.spf.com.tw'+relative
        name = 'sinopac_'+date.replace('/','-')+'.pdf'
        path = raw/name
        if not path.exists():
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            content = response.content
            if not content.startswith(b'%PDF'):
                raise ValueError('Expected PDF')
            path.write_bytes(content)
        values, reported = extract(path, date)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        prior = manifest.get(name, {})
        retrieved = prior.get('retrieved_at', now) if prior.get('sha256') == digest else now
        manifest[name] = {'source':url, 'retrieved_at':retrieved, 'sha256':digest,
                          'reported_observation_time':reported, 'reported_timezone':None}
        inputs.append(name)
        rows.append({'Date':datetime.strptime(date,'%Y/%m/%d').strftime('%m/%d/%Y'), **values})
        print(date, {k:v for k,v in values.items() if v}, flush=True)
    if len(rows)<15:
        raise ValueError('Archive unexpectedly incomplete')
    columns = sorted({k for r in rows for k in r if k!='Date'}, key=lambda k:int(k[1:].split('-')[0]))
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=['Date',*columns], restval=0)
    writer.writeheader()
    writer.writerows(rows)
    path = raw/'cme_2026-03-18.csv'
    path.write_text(out.getvalue(), encoding='utf-8', newline='')
    manifest[path.name] = {'source':INDEX, 'derived_from':inputs, 'retrieved_at':now,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'kind':'SinoPac archive of CME FedWatch tables; rounded to 0.1 percentage point; report-date end-of-day bound, not CME close'}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')


if __name__ == '__main__':
    main()
