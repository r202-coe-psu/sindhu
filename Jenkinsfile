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

        stage('Deploy to Staging') {
            when {
                branch 'develop'
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'sindhu-staging-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    string(credentialsId: 'sindhu-staging-host', variable: 'SSH_HOST'),
                    string(credentialsId: 'sindhu-staging-port', variable: 'SSH_PORT')
                ]) {
                    sh '''
                        # Deploy Sindhu Staging
                        echo '==> Deploying Sindhu to Staging..'
                        chmod 600 "$SSH_KEY"
                        ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$SSH_KEY" "$SSH_USER"@"$SSH_HOST" -p "$SSH_PORT" '
                            cd /home/projects/sindhu
                            sudo git -C /home/projects/sindhu pull
                            docker compose -f docker-compose.staging.yml up -d --build --force-recreate
                            '
                        echo "Staging deployment process finished successfully!"
                    '''
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
                        # Deploy Sindhu Production
                        echo '==> Deploying Sindhu to Production..'
                        echo "Target: ${SSH_USER}@${SSH_HOST}:${SSH_PORT}"
                        chmod 600 "$SSH_KEY"
                        ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$SSH_KEY" "$SSH_USER"@"$SSH_HOST" -p "$SSH_PORT" '
                            cd /home/projects/sindhu
                            sudo git -C /home/projects/sindhu pull
                            docker compose -f docker-compose.production.yml up -d --build --force-recreate
                            '
                        echo "Production deployment process finished successfully!"
                    '''
                }
            }
        }
    }
}