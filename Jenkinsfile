pipeline {
    agent any
    // We split the work into 3 stages:
    stages {
        // 1. Checkout the files from Git
        stage ('Prep') {
            steps {
                checkout scm
            }
        }
        // 2. Check if 'my-code.c' exists, 
        stage ('Build') {
            steps {
                script {
                    if (fileExists('my-code.c') == false) {
                        unstable('Code file not found!')
                    }
                }
            }
        }
        // 3. Dummy deploy
        // Print a message (only done if the build is stable)
        stage ('Deploy') {
            when { not { equals expected: 'UNSTABLE
            steps {
                echo 'Deploying it gently...'
            }
        }
    }
}
