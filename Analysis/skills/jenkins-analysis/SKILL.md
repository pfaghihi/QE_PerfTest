---
name: jenkins-analysis
description: Generate and open Analysis HTML reports from completed Jenkins JMeter builds or local JMeter CSV results in the QE_PerfTest project. Use for requests to analyze performance results or run the existing Analysis reporting workflow.
---

# Jenkins Analysis

Use the existing Python Analysis tool and its PowerShell launcher. This workflow reads completed results; it does not start tests, update jobs, or push code.

## Project and defaults

Use the current checkout if it contains `Analysis/report.py` and `Analysis/run-analysis.ps1`; otherwise use `C:/Users/c0679445/AI/PerfTest`. If neither exists, ask for the checkout location. Do not create another reporting implementation.

Defaults: Jenkins `http://localhost:8088`, job `QE_PerfTest`, build `lastCompletedBuild`, username `Pedram`, report `target/analysis/report.html`. Honor explicit server, job, build, username, output, or local-file selections. Test-type/environment values in reports are run labels, not inferred endpoint settings.

## Run the workflow

Generate a unique run ID (a GUID). Invoke `Analysis/run-analysis.ps1` with `-RunId` set to that ID. The launcher fetches results, generates HTML and JSON, verifies the output, and opens the HTML in the default browser. Use `-NoOpen` when the user requests generation only. It also accepts `-JenkinsUrl`, `-Job`, `-Build`, `-Username`, `-Output`, and `-InputFiles` for local CSV/JTL files.

For Jenkins access, use existing `JENKINS_USER` and `JENKINS_API_TOKEN` environment variables when available, checking presence without printing values. If they are unavailable, launch a visible interactive PowerShell window. The launcher presents a credential dialog: the password field takes the raw Jenkins user API token, not Base64 and not a GitHub token. Credentials are scoped to the process and restored/cleared after execution. Never request a token in chat or store it in scripts or command arguments.

Example default interactive launch from the project root (replace RUN_ID with the generated GUID):

```powershell
Start-Process powershell.exe -WindowStyle Normal -WorkingDirectory 'C:\Users\c0679445\AI\PerfTest' -ArgumentList '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'C:\Users\c0679445\AI\PerfTest\Analysis\run-analysis.ps1', '-RunId', 'RUN_ID'
```

Use the actual checkout path if different. Shell-quote user-supplied arguments safely. Interactive windows and browser launches may need runtime escalation; use the execution tool's permission mechanism. Do not add a separate confirmation step for fetching results or generating the report.

## Verify and report

The launcher writes `<RunId>.status.json` beside the output HTML. Read only the status for this invocation; an old HTML file or a successfully launched window does not prove completion. While waiting for credentials, tell the user where to enter them. Poll in short intervals and keep them informed. If input is still pending when yielding, say that clearly and check the same status when they return.

On `succeeded`, verify the referenced HTML/JSON exist, read the JSON, and provide a clickable report link plus the build number, sample count, error rate, P95, and P99. Mention whether the browser opened. Do not infer an SLA pass/fail result: the tool does not evaluate thresholds. For local inputs, state that the source is local rather than Jenkins.

On `failed`, report the actual error. A 401 requires a valid login ID/token pair; a 403 requires job/artifact read permission; missing artifacts require a completed build with archived CSV/JTL files. Retry only when the cause has been addressed or the user asks. Do not repeatedly reopen login windows or claim success based on stale files.

For CLI details or CSV requirements, read `Analysis/README.md` in the selected checkout. Failed Jenkins builds can still produce useful reports, so do not silently select `lastSuccessfulBuild` instead of the requested build.
