# Analysis

Python tool that reads archived JMeter CSV/JTL results from Jenkins and produces a standalone HTML report plus a JSON summary. Requires Python 3.10+; no third-party packages or installation needed. Run commands from the repository root.

## Read a Jenkins build

```powershell
python -m Analysis --username Pedram
```

Enter the **raw Jenkins user API token** at the hidden prompt. Use your actual Jenkins login ID if it differs from `Pedram`. The default server is `http://localhost:8088`, job is `QE_PerfTest`, and build is `lastCompletedBuild` (including failed builds). Credentials are not written to disk or included in the report.

Choose a specific build:

```powershell
python -m Analysis --jenkins-url http://localhost:8088 --job QE_PerfTest --build 12 --username Pedram --output target/analysis/build-12.html
```

Folder jobs use `--job "folder/job-name"`. The account needs read access to the job and archived artifacts. Anonymous servers can omit `--username`. For automated use, supply `JENKINS_USER` and `JENKINS_API_TOKEN` as environment variables through your secret manager or Jenkins credentials binding. Do not commit token values. HTTP redirects are rejected to avoid forwarding credentials; use the direct Jenkins URL.

The tool resolves a build alias to its build number before downloading artifacts. It downloads only `.csv`/`.jtl` files archived under `target/jmeter/results/`, which the existing Jenkinsfile already archives. It does not trigger builds, modify Jenkins, or change test pass/fail status.

## Open the report

For a single command that prompts in a Windows credential dialog, generates the report, and opens it:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Analysis\run-analysis.ps1
```

It reuses `JENKINS_USER` and `JENKINS_API_TOKEN` when both are already set. Add `-Build 12` for a specific build or `-NoOpen` to generate without opening a browser. Each run writes its own `<RunId>.status.json` beside the report so an agent can distinguish completion from an older report.

The reusable `jenkins-analysis` skill source is in `Analysis/skills/jenkins-analysis/SKILL.md`. Once installed, invoke it with:

```text
Use $jenkins-analysis to analyze the latest QE_PerfTest build and open the HTML report.
```

Or specify a build: `Use $jenkins-analysis for QE_PerfTest build 12.` Authentication still requires the credential dialog unless credentials are already supplied through environment variables.

Default outputs:

- `target/analysis/report.html`: open in any browser; charts and styles are embedded, with no CDN dependency.
- `target/analysis/report.json`: metrics and source metadata for further processing.

```powershell
Start-Process target/analysis/report.html
```

The HTML report includes sample count, error rate, request throughput, observed duration, P50/P95/P99 and max response times, request-level statistics, time trends, and failure messages. It also shows the Jenkins build result and available test parameters. It evaluates no performance thresholds.

## Analyze local results

```powershell
python -m Analysis --input target/jmeter/results/Order-api.csv
python -m Analysis --input first.csv second.csv --output target/analysis/combined.html
```

Use actual result filenames. Inputs must be UTF-8 CSV with headers `timeStamp`, `elapsed`, `label`, and `success`. Comma, semicolon, and tab delimiters are accepted. Timestamps must be epoch milliseconds; durations are milliseconds. Optional `responseCode`, `responseMessage`, and `failureMessage` enrich the error breakdown. XML JTL and aggregated rows (`SampleCount` other than 1) are rejected.

Percentiles use nearest rank and include failed samples. Throughput is sample count divided by the interval from the earliest sample start to latest sample completion. Each request's throughput uses its own interval. Samples may represent HTTP requests or transaction controllers, so the tool calls this requests/s rather than assuming business TPS. Charts bucket sample starts, include idle buckets, and use the actual span of a partial final bucket. Multiple files are combined without deduplicating samples; select distinct results, not duplicate exports. The tool loads samples into memory; large endurance runs require sufficient RAM.

## Verify

```powershell
python -m unittest Analysis.test_report -v
```

References: [Jenkins Remote Access API](https://www.jenkins.io/doc/book/using/remote-access-api/), [JMeter CSV results](https://jmeter.apache.org/usermanual/listeners.html).
