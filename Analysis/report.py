"""Download Jenkins JMeter CSV artifacts and render an offline HTML report."""
import argparse
import base64
import csv
import getpass
import html
import io
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class AnalysisError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward Jenkins credentials to login pages or artifact hosts.
        raise AnalysisError('Jenkins redirected the request. Use its direct server URL.')


class Jenkins:
    def __init__(self, url, username='', token=''):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AnalysisError('Use an HTTP(S) Jenkins URL without credentials, query, or fragment.')
        self.url = url.rstrip('/')
        self.headers = {'Accept': 'application/json'}
        if username:
            auth = base64.b64encode(f'{username}:{token}'.encode()).decode()
            self.headers['Authorization'] = f'Basic {auth}'
        self.opener = build_opener(NoRedirect())

    def get(self, path):
        try:
            with self.opener.open(Request(self.url + path, headers=self.headers), timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            explanations = {401: 'Check your Jenkins login ID and API token.', 403: 'Your account needs permission to read the job and its artifacts.', 404: 'The job, build, or artifact was not found.'}
            raise AnalysisError(f'Jenkins HTTP {exc.code}. {explanations.get(exc.code, "Request failed.")}') from None
        except (URLError, TimeoutError, OSError) as exc:
            raise AnalysisError(f'Could not read Jenkins: {exc.reason if isinstance(exc, URLError) else type(exc).__name__}') from None

    def results(self, job, build):
        parts = job.split('/')
        if any(not part or part in ('.', '..') for part in parts):
            raise AnalysisError('Job must be a name or folder/name path.')
        if not (build.isdigit() or build in ('lastCompletedBuild', 'lastSuccessfulBuild', 'lastBuild')):
            raise AnalysisError('Build must be a number, lastCompletedBuild, lastSuccessfulBuild, or lastBuild.')
        job_path = ''.join('/job/' + quote(part, safe='') for part in parts)
        query = '/api/json?tree=number,result,building,artifacts[relativePath],actions[parameters[name,value]]'
        try:
            info = json.loads(self.get(f'{job_path}/{build}{query}'))
        except (ValueError, UnicodeError):
            raise AnalysisError('Jenkins returned invalid JSON; check the server URL.') from None
        if info.get('building'):
            raise AnalysisError('This build is still running. Select a completed build.')
        number = info.get('number')
        if not isinstance(number, int) or number < 1:
            raise AnalysisError('Jenkins response did not contain a valid build number.')
        # Resolve aliases once; all artifact requests use the same immutable build.
        build_path = f'{job_path}/{number}'
        artifacts = []
        for artifact in info.get('artifacts', []):
            path = artifact.get('relativePath', '')
            parsed = PurePosixPath(path)
            if parsed.is_absolute() or '..' in parsed.parts or '\\' in path:
                continue
            if path.startswith('target/jmeter/results/') and parsed.suffix.lower() in ('.csv', '.jtl'):
                artifacts.append(path)
        if not artifacts:
            raise AnalysisError('No CSV/JTL artifacts under target/jmeter/results/. Confirm that this build ran JMeter and archived its results.')
        allowed = {'TEST_TYPE', 'ENVIRONMENT', 'THREADS', 'RAMP_UP', 'DURATION', 'API_HOST', 'API_PORT'}
        parameters = {p['name']: str(p.get('value', '')) for a in info.get('actions', []) for p in a.get('parameters', []) if p.get('name') in allowed}
        metadata = {'source': 'Jenkins', 'job': job, 'build': number, 'build_result': info.get('result', 'UNKNOWN'), 'url': self.url + build_path + '/', 'parameters': parameters, 'files': sorted(set(artifacts))}
        samples = []
        for path in metadata['files']:
            samples.extend(parse_csv(self.get(build_path + '/artifact/' + quote(path, safe='/')), path))
        return samples, metadata


def parse_csv(data, source):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        raise AnalysisError(f'{source}: expected UTF-8 CSV.') from None
    if text.lstrip().startswith('<'):
        raise AnalysisError(f'{source}: XML JTL is not supported; configure JMeter CSV output.')
    first = text.splitlines()[0] if text.strip() else ''
    delimiter = max((',', ';', '\t'), key=first.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    required = {'timeStamp', 'elapsed', 'label', 'success'}
    if not required.issubset(reader.fieldnames or []):
        raise AnalysisError(f'{source}: CSV needs timeStamp, elapsed, label, and success headers.')
    samples = []
    for row in reader:
        try:
            if None in row or any(row[key] is None for key in required):
                raise ValueError('column count')
            timestamp, elapsed = float(row['timeStamp']), float(row['elapsed'])
            if not all(math.isfinite(n) and n >= 0 for n in (timestamp, elapsed)):
                raise ValueError('invalid numeric value')
            success = row['success'].strip().lower()
            if success not in ('true', 'false') or int(row.get('SampleCount') or '1') != 1:
                raise ValueError('invalid or aggregated sample')
            samples.append({'start': timestamp, 'elapsed': elapsed, 'label': row['label'], 'success': success == 'true', 'code': row.get('responseCode') or '', 'message': row.get('failureMessage') or row.get('responseMessage') or ''})
        except (ValueError, TypeError):
            raise AnalysisError(f'{source}: invalid sample at CSV line {reader.line_num}; expected individual samples and epoch-millisecond timestamps.') from None
    if not samples:
        raise AnalysisError(f'{source}: no samples found.')
    return samples


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)]


def metrics(samples):
    values = [s['elapsed'] for s in samples]
    start = min(s['start'] for s in samples)
    end = max(s['start'] + s['elapsed'] for s in samples)
    duration = (end - start) / 1000
    failed = sum(not s['success'] for s in samples)
    return {'samples': len(samples), 'failed': failed, 'error_percent': failed * 100 / len(samples), 'mean_ms': sum(values) / len(values), 'p50_ms': percentile(values, 50), 'p95_ms': percentile(values, 95), 'p99_ms': percentile(values, 99), 'max_ms': max(values), 'duration_seconds': duration, 'throughput_rps': len(samples) / duration if duration else None, 'start_ms': start}


def summarize(samples, metadata):
    if not samples:
        raise AnalysisError('No samples to analyze.')
    overall = metrics(samples)
    groups = defaultdict(list)
    errors = Counter()
    for sample in samples:
        groups[sample['label']].append(sample)
        if not sample['success']:
            errors[(sample['label'], sample['code'], sample['message'])] += 1
    width = max(1, math.ceil(overall['duration_seconds'] / 60))
    buckets = defaultdict(list)
    for sample in samples:
        bucket = int((sample['start'] - overall['start_ms']) / (1000 * width))
        buckets[bucket].append(sample)
    trend = []
    for index in range(max(buckets) + 1):
        items = buckets[index]
        span = min(width, max(0, overall['duration_seconds'] - index * width))
        trend.append({'seconds': index * width, 'requests_per_second': len(items) / span if span else 0, 'mean_ms': sum(s['elapsed'] for s in items) / len(items) if items else 0, 'error_percent': 100 * sum(not s['success'] for s in items) / len(items) if items else 0})
    return {'metadata': metadata, 'overall': overall, 'requests': {label: metrics(items) for label, items in sorted(groups.items())}, 'errors': [{'label': label, 'code': code, 'message': message, 'count': count} for (label, code, message), count in errors.most_common()], 'trend': trend, 'bucket_seconds': width}


def escape(value):
    return html.escape(str(value), quote=True)


def chart(trend, key, title, unit):
    values = [item[key] for item in trend]
    peak = max(values) if values else 0
    points = ' '.join(f'{45 + i * 690 / max(1, len(values) - 1):.1f},{160 - value * 125 / (peak or 1):.1f}' for i, value in enumerate(values))
    return f'<section class="chart"><h3>{title}</h3><svg viewBox="0 0 760 195" role="img" aria-label="{title}"><path d="M45 30 V160 H735" fill="none" stroke="#b8c7d6"/><polyline points="{points}" fill="none" stroke="#087f8c" stroke-width="3"/><text x="45" y="20">Peak {peak:,.2f} {unit}</text><text x="45" y="185">0s</text><text x="660" y="185">{trend[-1]["seconds"]}s</text></svg></section>'


def render(report):
    m, meta = report['overall'], report['metadata']
    def number(value):
        return 'N/A' if value is None else f'{value:,.2f}'
    cards = [('Samples', f'{m["samples"]:,}'), ('Error rate', f'{m["error_percent"]:.2f}%'), ('Throughput', number(m['throughput_rps']) + ' req/s'), ('P95', number(m['p95_ms']) + ' ms'), ('P99', number(m['p99_ms']) + ' ms'), ('Observed duration', number(m['duration_seconds']) + ' s')]
    card_html = ''.join(f'<div class="card"><span>{label}</span><strong>{value}</strong></div>' for label, value in cards)
    rows = ''.join('<tr><td>' + escape(label) + '</td>' + ''.join(f'<td>{number(stats[key])}</td>' for key in ('samples', 'mean_ms', 'p50_ms', 'p95_ms', 'p99_ms', 'max_ms', 'throughput_rps', 'error_percent')) + '</tr>' for label, stats in report['requests'].items())
    errors = ''.join(f'<tr><td>{escape(e["label"])}</td><td>{escape(e["code"])}</td><td>{escape(e["message"])}</td><td>{e["count"]}</td></tr>' for e in report['errors']) or '<tr><td colspan="4">No failed samples.</td></tr>'
    params = ''.join(f'<span class="tag">{escape(k)}: {escape(v)}</span>' for k, v in meta.get('parameters', {}).items())
    source = escape(meta.get('job', 'Local results'))
    if meta.get('build'):
        source += f' · Build {meta["build"]} · Jenkins result: {escape(meta["build_result"])}'
    source_link = f'<a href="{escape(meta["url"])}">Open Jenkins build</a>' if meta.get('url') else ''
    charts = chart(report['trend'], 'mean_ms', 'Mean response time', 'ms') + chart(report['trend'], 'requests_per_second', 'Request throughput', 'req/s') + chart(report['trend'], 'error_percent', 'Error rate', '%')
    files = ''.join(f'<li>{escape(path)}</li>' for path in meta['files'])
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Analysis — JMeter results</title>
<style>body{{margin:0;background:#f1f5f9;color:#172a3a;font:15px system-ui,sans-serif}}header{{background:#102b3f;color:white;padding:36px max(24px,calc((100% - 1200px)/2))}}h1{{font-size:38px;margin:0 0 8px}}header p{{color:#bbd2df}}main{{max-width:1200px;margin:24px auto;padding:0 24px}}a{{color:#4dd3d0}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}.card,section{{background:white;border:1px solid #dce5ed;border-radius:10px;padding:20px;margin-bottom:20px}}.card span{{display:block;color:#536775;font-size:13px}}.card strong{{display:block;font-size:25px;margin-top:10px}}.tag{{display:inline-block;background:#23465d;padding:6px 10px;margin:3px;border-radius:5px;font-size:12px}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:12px;text-align:right;border-bottom:1px solid #e3eaf0}}th:first-child,td:first-child{{text-align:left}}th{{background:#f4f8fb;white-space:nowrap}}td{{overflow-wrap:anywhere}}.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}svg{{width:100%;height:auto}}svg text{{font-size:13px;fill:#536775}}h2{{font-size:21px}}h3{{font-size:16px;margin-top:0}}footer{{color:#536775;font-size:13px;padding:10px 0 30px}}@media print{{header{{background:white;color:black}}.card,section{{break-inside:avoid}}}}</style></head>
<body><header><h1>Analysis</h1><p>JMeter performance report · {source}</p>{source_link}<div>{params}</div></header>
<main><div class="cards">{card_html}</div><div class="charts">{charts}</div>
<section><h2>Request metrics</h2><div class="scroll"><table><thead><tr><th>Request</th><th>Samples</th><th>Mean ms</th><th>P50 ms</th><th>P95 ms</th><th>P99 ms</th><th>Max ms</th><th>Req/s</th><th>Error %</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section><h2>Failed samples</h2><div class="scroll"><table><thead><tr><th>Request</th><th>Code</th><th>Message</th><th>Count</th></tr></thead><tbody>{errors}</tbody></table></div></section>
<section><h2>Source files</h2><ul>{files}</ul></section>
<footer>Generated {generated}. Percentiles use nearest rank and include successful and failed samples. Throughput is sample count divided by the observed interval from earliest start to latest completion; per-request rates use each request's interval. Charts group sample starts into {report['bucket_seconds']}-second buckets, including idle buckets. Requests are JMeter samples, not necessarily business transactions. No performance thresholds were evaluated. Files are combined without deduplication; use distinct, non-overlapping results.</footer></main></body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description='Analysis: create an HTML report from Jenkins JMeter artifacts or local CSV/JTL files.')
    parser.add_argument('--input', nargs='+', type=Path, help='Local result files (skips Jenkins).')
    parser.add_argument('--jenkins-url', default='http://localhost:8088')
    parser.add_argument('--job', default='QE_PerfTest', help='Job or folder/job path.')
    parser.add_argument('--build', default='lastCompletedBuild')
    parser.add_argument('--username', default=os.environ.get('JENKINS_USER', ''))
    parser.add_argument('--output', type=Path, default=Path('target/analysis/report.html'))
    args = parser.parse_args(argv)
    try:
        if args.input:
            paths = list(dict.fromkeys(path.resolve() for path in args.input))
            samples = [sample for path in paths for sample in parse_csv(path.read_bytes(), path.name)]
            metadata = {'source': 'local', 'files': [str(path) for path in paths], 'parameters': {}}
        else:
            token = os.environ.get('JENKINS_API_TOKEN', '')
            if token and not args.username:
                raise AnalysisError('Set JENKINS_USER or --username when using JENKINS_API_TOKEN.')
            if args.username and not token:
                if not sys.stdin.isatty():
                    raise AnalysisError('Set JENKINS_API_TOKEN for noninteractive use.')
                token = getpass.getpass('Jenkins API token (hidden): ')
            samples, metadata = Jenkins(args.jenkins_url, args.username, token).results(args.job, args.build)
        report = summarize(samples, metadata)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(report), encoding='utf-8')
        args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Analysis report: {args.output.resolve()}')
        print(f'{report["overall"]["samples"]} samples; {report["overall"]["error_percent"]:.2f}% errors')
        return 0
    except (AnalysisError, OSError, csv.Error) as exc:
        print(f'Analysis: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
