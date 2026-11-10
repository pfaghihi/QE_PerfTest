# Order API JMeter tests

The [Analysis Python tool](Analysis/README.md) downloads archived JMeter results from Jenkins and builds a standalone HTML performance report. Run `python -m Analysis --username YOUR_JENKINS_LOGIN` from this folder; it securely prompts for an API token.

Maven runs the existing `Order-api.jmx` in non-GUI mode with JMeter 5.6.3 and the Ultimate Thread Group extension. Requires Java 8+ and Maven 3.9+; first setup needs access to Maven Central.

## Run

Start the Order API on `localhost:8081`, then run:

```powershell
mvn clean verify
```

Override the destination if needed:

```powershell
mvn clean verify "-Dapi.host=localhost" "-Dapi.port=8081"
```

The default JMX load schedule uses 100 users, zero initial delay, a 60-second ramp-up, a 239-second hold, and a 1-second shutdown (300 seconds total). The separate Sanity Test group remains disabled. Requests include `GET /ping`, `POST /api/customers`, and `GET /api/customers`; the POST can create data and currently sends no body, as in the original script.

Results are written under `target/jmeter/results`, HTML dashboards under `target/jmeter/reports`, and logs under `target/jmeter/logs`. Open the generated report's `index.html`. Any failed sample fails the Maven verification step.

## Edit or prepare

Continue editing `Order-api.jmx` in JMeter. Reload it after external edits before saving from an already-open GUI. Host and port use JMeter properties with defaults, so the plan also works directly in JMeter. Maven downloads its own JMeter runtime and required extension.

To prepare the runtime without sending API requests:

```powershell
mvn jmeter:configure
```

## Jenkins

Commit `Jenkinsfile`, `pom.xml`, and `Order-api.jmx` to your Git repository. Create a Jenkins **Pipeline** job with **Pipeline script from SCM**, select Git, enter the repository URL and credentials, and set the script path to `Jenkinsfile`. A Multibranch Pipeline also works.

The pipeline checks out the configured repository revision, runs the test, and archives CSV results, HTML dashboards, and logs even when samples fail. The agent needs Git, Java, Maven 3.9+, and access to Maven Central and the API. Maven and Java must be on its PATH.

Set `API_HOST` and `API_PORT` in **Build with Parameters**. `localhost` refers to the Jenkins agent; for a containerized agent, use a hostname that reaches your API outside that container. The API must already be running.

The pipeline uses the `jenkins-parameterized` Maven profile with these build parameters:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `TEST_TYPE` | `smoke` | Run label: smoke, load, stress, or endurance. Does not change the load automatically. |
| `ENVIRONMENT` | `qa` | Run label: qa or uat. Host and port still select the actual destination. |
| `THREADS` | `100` | Concurrent users. |
| `RAMP_UP` | `60` | Ramp-up in seconds. |
| `DURATION` | `300` | Total scheduled load in seconds, including ramp-up and 1-second shutdown. |

The hold period is `DURATION - RAMP_UP - 1`, which must be positive. The default schedule is 60 seconds ramp-up, 239 seconds hold, and 1 second shutdown. Test type and environment appear in the Jenkins build name and are forwarded as JMeter properties `test.type` and `test.environment`. All types run the same `Order-api.jmx`; choose load values appropriate to the selected type.

Setup, downloads, in-flight request completion, and report generation add to the build time. The execution timeout allows `DURATION` plus 15 minutes for overhead, including endurance runs. Maven verification fails on failed samples; TPS/P95/P99 thresholds are not configured. Normal Maven runs use the parameter defaults in the JMX.

## JMX parameters

`Order-api.jmx` exposes the five run parameters under **Test Plan > User Defined Variables**. These variables read JMeter properties; the Ultimate Thread Group reads the same load properties and calculates its hold period directly. Maven forwards the properties without using a `threads_schedule` override.

| JMX variable | JMeter property | Default |
| --- | --- | --- |
| `TEST_TYPE` | `test.type` | `smoke` |
| `ENVIRONMENT` | `test.environment` | `qa` |
| `THREADS` | `load.threads` | `100` |
| `RAMP_UP` | `load.rampup` | `60` |
| `DURATION` | `load.duration` | `300` |

Set properties with `-J` when running JMeter directly (or in JMeter's `user.properties` for GUI runs). Editing only the displayed variable value does not override the properties read by the thread group. Direct runs must use positive threads, nonnegative ramp-up, and duration greater than ramp-up plus 1 second. Jenkins validates these before execution. Clear any old `threads_schedule` property, which would override the JMX schedule.

```powershell
jmeter -n -t Order-api.jmx -Jtest.type=load -Jtest.environment=uat -Jload.threads=10 -Jload.rampup=5 -Jload.duration=60 -l results.jtl
```

For Maven:

```powershell
mvn clean verify -Pjenkins-parameterized "-Dtest.type=load" "-Dtest.environment=uat" "-Dload.threads=10" "-Dload.rampup=5" "-Dload.duration=60"
```

After Jenkins loads the updated Jenkinsfile, the new parameters appear under **Build with Parameters**. The older `jenkins-60s` profile remains available for local 60-second runs.

To run the original 60-second profile locally:

```powershell
mvn clean verify -Pjenkins-60s
```

References: [JMeter Maven plugin](https://github.com/jmeter-maven-plugin/jmeter-maven-plugin), [Ultimate Thread Group schedule override](https://jmeter-plugins.org/wiki/UltimateThreadGroup/), [Jenkins SCM checkout](https://www.jenkins.io/doc/pipeline/steps/workflow-scm-step/).
