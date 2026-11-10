# Order API JMeter tests

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

The existing load schedule uses 3 users, a 1-second initial delay, a 3-second ramp-up, a 60-second hold, and a 10-second shutdown. The separate Sanity Test group remains disabled. Requests include `GET /ping`, `POST /api/customers`, and `GET /api/customers`; the POST can create data and currently sends no body, as in the original script.

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

The `jenkins-60s` Maven profile overrides the Ultimate Thread Group schedule with 3 users, zero initial delay, 1 second ramp-up, 58 seconds hold, and 1 second shutdown: 60 seconds total scheduled load. Setup, downloads, in-flight request completion, and report generation add to the overall build time. The pipeline has a separate 20-minute timeout. Normal Maven runs keep the schedule saved in the JMX.

To run the same profile locally:

```powershell
mvn clean verify -Pjenkins-60s
```

References: [JMeter Maven plugin](https://github.com/jmeter-maven-plugin/jmeter-maven-plugin), [Ultimate Thread Group schedule override](https://jmeter-plugins.org/wiki/UltimateThreadGroup/), [Jenkins SCM checkout](https://www.jenkins.io/doc/pipeline/steps/workflow-scm-step/).
