import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Analysis.report import AnalysisError, Jenkins, NoRedirect, main, parse_csv, render, summarize


CSV = b'''timeStamp,elapsed,label,responseCode,success,responseMessage
1000,100,GET orders,200,true,OK
2000,200,GET orders,200,true,OK
3000,300,POST orders,500,false,"failure, retry"
4000,400,<script>alert(1)</script>,503,false,<img src=x onerror=alert(1)>
'''


class AnalysisTests(unittest.TestCase):
    def test_metrics_and_escaping(self):
        report = summarize(parse_csv(CSV, 'fixture.csv'), {'files': ['fixture.csv']})
        metrics = report['overall']
        self.assertEqual(metrics['samples'], 4)
        self.assertEqual(metrics['failed'], 2)
        self.assertEqual(metrics['mean_ms'], 250)
        self.assertEqual(metrics['p50_ms'], 200)
        self.assertEqual(metrics['p95_ms'], 400)
        self.assertAlmostEqual(metrics['throughput_rps'], 4 / 3.4)
        self.assertEqual(report['errors'][0]['message'], 'failure, retry')
        page = render(report)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<img src=x', page)

    def test_invalid_and_empty_data(self):
        for data in (b'', b'timeStamp,elapsed,label,success\n', b'<testResults/>', b'timeStamp,elapsed,label,success\n1000,NaN,x,true', b'timeStamp,elapsed,label,success\n1000,5,x,maybe', b'timeStamp,elapsed,label,success,SampleCount\n1000,5,x,true,2'):
            with self.subTest(data=data), self.assertRaises(AnalysisError):
                parse_csv(data, 'bad.csv')

    def test_semicolon_and_zero_interval(self):
        samples = parse_csv(b'\xef\xbb\xbftimeStamp;elapsed;label;success\n1000;0;x;true\n', 'test.jtl')
        report = summarize(samples, {'files': []})
        self.assertIsNone(report['overall']['throughput_rps'])
        self.assertIn('N/A req/s', render(report))

    def test_idle_buckets(self):
        samples = parse_csv(b'timeStamp,elapsed,label,success\n0,10,x,true\n3000,10,x,true\n', 'test.csv')
        report = summarize(samples, {'files': []})
        self.assertEqual(report['trend'][1]['requests_per_second'], 0)
        self.assertEqual(report['trend'][2]['requests_per_second'], 0)

    def test_jenkins_pins_alias_and_filters_artifacts_and_secrets(self):
        info = {'number': 42, 'building': False, 'result': 'FAILURE', 'artifacts': [{'relativePath': 'target/jmeter/results/Order api.csv'}, {'relativePath': 'target/jmeter/reports/statistics.csv'}, {'relativePath': 'target/jmeter/results/../../private.csv'}], 'actions': [{'parameters': [{'name': 'THREADS', 'value': '100'}, {'name': 'SECRET', 'value': 'do-not-export'}]}]}
        client = Jenkins('http://localhost:8088', 'user', 'token')
        with patch.object(client, 'get', side_effect=[json.dumps(info).encode(), CSV]) as get:
            samples, metadata = client.results('folder/QE PerfTest', 'lastCompletedBuild')
        self.assertEqual(len(samples), 4)
        self.assertIn('/job/folder/job/QE%20PerfTest/lastCompletedBuild/api/json', get.call_args_list[0].args[0])
        self.assertEqual(get.call_args_list[1].args[0], '/job/folder/job/QE%20PerfTest/42/artifact/target/jmeter/results/Order%20api.csv')
        self.assertEqual(metadata['parameters'], {'THREADS': '100'})
        self.assertEqual(metadata['build_result'], 'FAILURE')
        self.assertNotIn('token', json.dumps(metadata))

    def test_running_or_missing_artifacts(self):
        for info in ({'number': 1, 'building': True}, {'number': 1, 'building': False, 'artifacts': []}):
            client = Jenkins('http://localhost:8088')
            with patch.object(client, 'get', return_value=json.dumps(info).encode()), self.assertRaises(AnalysisError):
                client.results('QE_PerfTest', 'lastBuild')

    def test_no_credential_redirect(self):
        with self.assertRaises(AnalysisError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'http://elsewhere/')

    def test_cli_writes_html_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'input.csv').write_bytes(CSV)
            output = path / 'report.html'
            self.assertEqual(main(['--input', str(path / 'input.csv'), '--output', str(output)]), 0)
            self.assertIn('Analysis', output.read_text(encoding='utf-8'))
            self.assertEqual(json.loads(output.with_suffix('.json').read_text())['overall']['samples'], 4)


if __name__ == '__main__':
    unittest.main()
