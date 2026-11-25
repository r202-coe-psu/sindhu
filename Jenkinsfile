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
                            sudo git -C /home/projects/sindhu checkout develop
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

    post {
        always {
            // Discord notification (ci/README.md). Never fails the build: a missing credential,
            // a missing script or a Discord outage only logs a warning.
            script {
                if (!(env.BRANCH_NAME in ['develop', 'main'])) {
                    return
                }
                try {
                    if (fileExists('ci/discord-notify.sh')) {
                        withCredentials([string(credentialsId: 'sindhu-discord-webhook-ci', variable: 'DISCORD_WEBHOOK_URL')]) {
                            withEnv([
                                'NOTIFY_KIND=deploy',
                                'NOTIFY_USERNAME=Sindhu Deploy',
                                "NOTIFY_TARGET=${env.BRANCH_NAME == 'main' ? 'prod' : 'staging'}",
                                "NOTIFY_RESULT=${currentBuild.currentResult}",
                                "NOTIFY_JOB=${env.JOB_NAME ?: ''}",
                                "NOTIFY_BRANCH=${env.BRANCH_NAME ?: ''}",
                                "NOTIFY_BUILD_NUMBER=${env.BUILD_NUMBER ?: ''}",
                                "NOTIFY_BUILD_URL=${env.BUILD_URL ?: ''}",
                                "NOTIFY_COMMIT=${env.GIT_COMMIT ?: ''}",
                                "NOTIFY_DURATION=${currentBuild.durationString.replace(' and counting', '')}"
                            ]) {
                                def rc = sh(script: './ci/discord-notify.sh', returnStatus: true)
                                if (rc != 0) {
                                    echo "WARNING: Discord notification failed (exit ${rc}); ignoring."
                                }
                            }
                        }
                    } else {
                        echo 'WARNING: ci/discord-notify.sh not found in workspace; skipping Discord notification.'
                    }
                } catch (err) {
                    echo "WARNING: Discord notification skipped: ${err.message}"
                }
            }
        }
    }
}
