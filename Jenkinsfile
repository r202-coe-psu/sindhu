pipeline {
    agent { label 'mgmt' }

    stages {
        stage('Checkout') {
            when {
                anyOf {
                    branch 'develop'
                    branch 'main'
                }
            }
            steps {
                checkout scm
            }
        }

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
                    withCredentials([string(credentialsId: 'SONARQUBE_TOKEN', variable: 'SONAR_TOKEN')]) {
                        withSonarQubeEnv() {
                            sh "${scannerHome}/bin/sonar-scanner -Dsonar.login=${SONAR_TOKEN}"
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
                        echo "Starting deployment to Production server..."
                        # [1] Connect to proxy server 
                        ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST "

                            # [2] Deploy Sindhu
                            echo '==> Deploying Sindhu..'
                            ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519_r202cid $SSH_USER@r202-sindhu '
                                cd /home/projects/sindhu
                                sudo git -C /home/projects/sindhu pull
                                docker compose -f docker-compose.production.yml up -d --build --force-recreate
                                '
                        "
                        echo "Deployment process finished successfully!"
                    '''
                }
            }
        }
    }
}