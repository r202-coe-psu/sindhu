pipeline {
    agent { label 'mgmt' }

    stages {
        stage('SonarQube Analysis') {
            when {
                anyOf {
                    branch 'develop'
                    branch 'main'
                }
            }
            steps {
                script {
                    def scannerHome = tool 'SonarScanner'
                    withCredentials([string(credentialsId: 'SINDHU_SONAR_TOKEN', variable: 'SONAR_TOKEN')]) {
                        withSonarQubeEnv() {
                            sh "${scannerHome}/bin/sonar-scanner -Dsonar.token=\$SONAR_TOKEN"
                        }
                    }
                }
            }
        }

        stage('Deploy to Production') {
            when {
                branch 'main'
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'sindhu-prod-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    string(credentialsId: 'sindhu-prod-host', variable: 'SSH_HOST'),
                    string(credentialsId: 'sindhu-prod-port', variable: 'SSH_PORT')
                ]) {
                    sh '''
                        # [2] Deploy Sindhu
                        echo '==> Deploying Sindhu..'
                        ssh -i $SSH_KEY $SSH_USER@r202-sindhu '
                            cd /home/projects/sindhu
                            sudo git -C /home/projects/sindhu pull
                            docker compose -f docker-compose.production.yml up -d --build --force-recreate
                            '
                        echo "Deployment process finished successfully!"
                    '''
                }
            }
        }
    }
}