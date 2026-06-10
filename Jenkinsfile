pipeline {
    agent { label 'mgmt' }

    environment {
        IMAGE_SINDHU  = 'sindhu/sindhu:latest'
        IMAGE_MAGEAI  = 'mageai-sindhu-image'
        TAR_SINDHU    = 'sindhu-image.tar'
        TAR_MAGEAI    = 'mageai-image.tar'
        TARGET_DIR    = '/home/projects/sindhu'
    }

    stages {
        stage('Checkout Code') {
            when { branch 'main' }
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            when { branch 'main' }
            steps {
                echo '==> Building Docker Image on Management Node...'
                sh "docker compose -f docker-compose.production.yml build"
            }
        }

        stage('Export Sindhu Image') {
            when { branch 'main' }
            steps {
                echo '==> Saving Sindhu Image to .tar file...'
                sh "docker save -o ${TAR_SINDHU} ${IMAGE_SINDHU}"
            }
        }

        stage('Export MageAI Image') {
            when { branch 'main' }
            steps {
                echo '==> Saving MageAI Image to .tar file...'
                sh "docker save -o ${TAR_MAGEAI} ${IMAGE_MAGEAI}"
            }
        }

        stage('Transfer Image & Config') {
            when { branch 'main' }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'sindhu-prod-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    string(credentialsId: 'sindhu-prod-host', variable: 'SSH_HOST'),
                    string(credentialsId: 'sindhu-prod-port', variable: 'SSH_PORT')
                ]) {
                    echo '==> Transferring Image and Compose file via Proxy Server...'
                    sh '''
                        set -e
                        # 1. send .tar and docker-compose to proxy
                        scp -i $SSH_KEY -P $SSH_PORT -o StrictHostKeyChecking=no ${TAR_SINDHU} ${TAR_MAGEAI} docker-compose.production.yml $SSH_USER@$SSH_HOST:~/

                        # 2. send to r202-sindhu from proxy
                        ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST "
                            set -e
                            scp -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519_r202cid ~/${TAR_SINDHU} ~/${TAR_MAGEAI} ~/docker-compose.production.yml $SSH_USER@r202-sindhu:~/
                            rm -f ~/${TAR_SINDHU} ~/${TAR_MAGEAI} ~/docker-compose.production.yml
                        "
                    '''
                }
            }
        }

        stage('Load Image on Production') {
            when { branch 'main' }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'sindhu-prod-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    string(credentialsId: 'sindhu-prod-host', variable: 'SSH_HOST'),
                    string(credentialsId: 'sindhu-prod-port', variable: 'SSH_PORT')
                ]) {
                    echo '==> Loading Docker Image on target server...'
                    sh '''
                        set -e
                        # สั่งผ่าน Proxy -> ไปยังเครื่อง r202-sindhu เพื่อทำ docker load
                        ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST "
                            ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519_r202cid $SSH_USER@r202-sindhu '
                                set -e
                                echo \"--> Executing docker load for Sindhu...\"
                                sudo docker load -i ~/${TAR_SINDHU}
                                rm -f ~/${TAR_SINDHU}
                                echo \"--> Executing docker load for MageAI...\"
                                sudo docker load -i ~/${TAR_MAGEAI}
                                rm -f ~/${TAR_MAGEAI}
                            '
                        "
                    '''
                }
            }
        }

        stage('Deploy to Production') {
            when { branch 'main' }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'sindhu-prod-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    string(credentialsId: 'sindhu-prod-host', variable: 'SSH_HOST'),
                    string(credentialsId: 'sindhu-prod-port', variable: 'SSH_PORT')
                ]) {
                    echo '==> Deploying Sindhu Containers...'
                    sh '''
                        set -e
                        ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST "
                            ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519_r202cid $SSH_USER@r202-sindhu '
                                set -e
                                # ย้ายไฟล์ compose ไปไว้ที่โฟลเดอร์โปรเจกต์
                                sudo mkdir -p ${TARGET_DIR}
                                sudo mv ~/docker-compose.production.yml ${TARGET_DIR}/docker-compose.production.yml
                                
                                cd ${TARGET_DIR}
                                
                                echo \"--> Pulling latest source code from git...\"
                                sudo git pull origin main
                                
                                # รันโดยใช้ Image ใหม่ที่เราเพิ่งโหลดเข้าไป ไม่ต้องใช้ --build แล้ว
                                sudo docker compose -f docker-compose.production.yml up -d --force-recreate
                            '
                        "
                        echo "Deployment process finished successfully!"
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Cleaning up workspace artifact...'
            sh "rm -f ${TAR_SINDHU} ${TAR_MAGEAI}"
        }
    }
}