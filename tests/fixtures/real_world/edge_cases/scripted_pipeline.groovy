node('linux') {
    stage('Build') {
        sh 'make build'
    }
    stage('Test') {
        sh 'make test'
    }
}
