pipeline {
    agent any

    parameters {
        string(name: 'HOST', defaultValue: '0.0.0.0', description: 'Host of the service')
        string(name: 'PORT', defaultValue: '1234', description: 'Port of the service')
    }

    environment {
        API_KEY = 'S3CR3T-KEY'  // Aquí puedes usar 'credentials' si tienes configurada una credencial en Jenkins
        API_URL = 'http://pensive_kapitsa.orb.local:5000/check-connection'
    }

    stages {
        stage('Test Connection') {
            steps {
                script {
                    def response = sh(
                        script: """
                            curl -s -o /dev/null -w "%{http_code}" \
                            -X POST $API_URL \
                            -H "Content-Type: application/json" \
                            -H "x-api-key: $API_KEY" \
                            -d '{\"host\": \"${HOST}\", \"port\": ${PORT}}'
                        """,
                        returnStdout: true
                    ).trim()

                    echo "HTTP Response: ${response}"

                    if (response == '200') {
                        echo "Conexión exitosa a ${HOST}:${PORT}"
                    } else if (response == '403') {
                        error "No tienes la llave correcta, por favor contacta al administrador del servicio"
                    } else {
                        error "Error al conectar a ${HOST}:${PORT}. Código de estado: ${response}. Documentation: https://localhost:1234/docs"
                    }
                }
            }
        }
    }
}