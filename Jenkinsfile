pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        choice(name: 'TEST_TYPE', choices: ['smoke', 'load', 'stress', 'endurance'], description: 'Run classification; set the load using THREADS, RAMP_UP, and DURATION.')
        choice(name: 'ENVIRONMENT', choices: ['qa', 'uat'], description: 'Environment label; API_HOST and API_PORT specify the actual destination.')
        string(name: 'THREADS', defaultValue: '100', description: 'Number of concurrent users.')
        string(name: 'RAMP_UP', defaultValue: '60', description: 'Ramp-up time in seconds.')
        string(name: 'DURATION', defaultValue: '300', description: 'Total scheduled load time in seconds, including ramp-up and 1-second shutdown.')
        string(name: 'API_HOST', defaultValue: 'localhost', description: 'API hostname reachable from the Jenkins agent (no scheme or path).')
        string(name: 'API_PORT', defaultValue: '8081', description: 'Order API port.')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate configuration') {
            steps {
                script {
                    if (!(params.TEST_TYPE in ['smoke', 'load', 'stress', 'endurance']) || !(params.ENVIRONMENT in ['qa', 'uat'])) {
                        error('Unsupported TEST_TYPE or ENVIRONMENT.')
                    }
                    ['THREADS', 'RAMP_UP', 'DURATION'].each { name ->
                        if (!(params[name] ==~ /[0-9]{1,7}/)) {
                            error("${name} must be an integer between 0 and 9999999.")
                        }
                    }
                    if (params.THREADS.toInteger() < 1) {
                        error('THREADS must be at least 1.')
                    }
                    if (params.DURATION.toInteger() <= params.RAMP_UP.toInteger() + 1) {
                        error('DURATION must exceed RAMP_UP + 1 second to allow a hold period and shutdown.')
                    }
                    env.HOLD_SECONDS = (params.DURATION.toInteger() - params.RAMP_UP.toInteger() - 1).toString()
                    currentBuild.displayName = "#${env.BUILD_NUMBER} ${params.TEST_TYPE} / ${params.ENVIRONMENT}"
                    currentBuild.description = "${params.THREADS} users; ${params.RAMP_UP}s ramp; ${params.DURATION}s total"
                    if (!(params.API_HOST ==~ /[A-Za-z0-9][A-Za-z0-9.-]*/)) {
                        error('API_HOST must be a hostname or IPv4 address, without a scheme or path.')
                    }
                    if (!(params.API_PORT ==~ /[0-9]{1,5}/) || params.API_PORT.toInteger() < 1 || params.API_PORT.toInteger() > 65535) {
                        error('API_PORT must be between 1 and 65535.')
                    }
                    if (!fileExists('Order-api.jmx') || !fileExists('pom.xml')) {
                        error('The checked-out repository must contain Order-api.jmx and pom.xml.')
                    }
                }
            }
        }

        stage('Execute JMeter') {
            steps {
                script {
                    // Allow setup/reporting overhead as well as long endurance runs.
                    timeout(time: params.DURATION.toInteger() + 900, unit: 'SECONDS') {
                        if (isUnix()) {
                            sh 'mvn -B -ntp clean verify -Pjenkins-parameterized "-Dapi.host=$API_HOST" "-Dapi.port=$API_PORT" "-Dtest.type=$TEST_TYPE" "-Dtest.environment=$ENVIRONMENT" "-Dload.threads=$THREADS" "-Dload.rampup=$RAMP_UP" "-Dload.hold=$HOLD_SECONDS"'
                        } else {
                            bat 'mvn -B -ntp clean verify -Pjenkins-parameterized "-Dapi.host=%API_HOST%" "-Dapi.port=%API_PORT%" "-Dtest.type=%TEST_TYPE%" "-Dtest.environment=%ENVIRONMENT%" "-Dload.threads=%THREADS%" "-Dload.rampup=%RAMP_UP%" "-Dload.hold=%HOLD_SECONDS%"'
                        }
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'target/jmeter/results/**,target/jmeter/reports/**,target/jmeter/logs/**', allowEmptyArchive: true
                }
            }
        }
    }
}
