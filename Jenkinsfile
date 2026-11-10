pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
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

        stage('Run 60-second JMeter test') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'mvn -B -ntp clean verify -Pjenkins-60s "-Dapi.host=$API_HOST" "-Dapi.port=$API_PORT"'
                    } else {
                        bat 'mvn -B -ntp clean verify -Pjenkins-60s "-Dapi.host=%API_HOST%" "-Dapi.port=%API_PORT%"'
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
