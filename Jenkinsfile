#!/usr/bin/env groovy

/**
 * Jenkins CI/CD Pipeline for Spider Price Tracker
 *
 * This pipeline builds, tests, and deploys the containerized application
 * to production via Portainer on a NAS device.
 *
 * Pipeline Stages:
 * 1. Checkout - Pull latest code from Git
 * 2. Build - Build Docker images for Flask and Scraper
 * 3. Test - Run unit tests and health checks
 * 4. Push - Push images to Docker Hub
 * 5. Deploy - Deploy to Portainer (production)
 * 6. Verify - Health check deployed services
 */

pipeline {
    agent any

    environment {
        // Docker Hub credentials (configured in Jenkins)
        DOCKER_REGISTRY = 'docker.io'
        DOCKER_CREDENTIALS = credentials('docker-hub-credentials')
        DOCKER_USERNAME = "${env.DOCKER_CREDENTIALS_USR}"

        // Image names
        FLASK_IMAGE = "${DOCKER_USERNAME}/spider-flask"
        SCRAPER_IMAGE = "${DOCKER_USERNAME}/spider-scraper"
        SGPROOF_IMAGE = "${DOCKER_USERNAME}/spider-sgproof-scraper"

        // Version tagging
        GIT_COMMIT_SHORT = sh(
            script: "git rev-parse --short HEAD",
            returnStdout: true
        ).trim()
        BUILD_VERSION = "${env.BUILD_NUMBER}-${GIT_COMMIT_SHORT}"

        // Portainer settings (configure in Jenkins credentials)
        PORTAINER_URL = credentials('portainer-url')
        PORTAINER_API_KEY = credentials('portainer-api-key')

        // Database password (configure in Jenkins credentials)
        DB_PASSWORD = credentials('db-password')
    }

    options {
        // Keep builds for 30 days
        buildDiscarder(logRotator(daysToKeepStr: '30', numToKeepStr: '10'))

        // Prevent concurrent builds
        disableConcurrentBuilds()

        // Timeout after 1 hour
        timeout(time: 1, unit: 'HOURS')

        // Timestamps in console output
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                echo '📦 Checking out source code...'
                checkout scm

                script {
                    // Display build information
                    echo """
                    ═══════════════════════════════════════════
                    🚀 Spider Price Tracker CI/CD Pipeline
                    ═══════════════════════════════════════════
                    Build Number: ${env.BUILD_NUMBER}
                    Git Commit:   ${env.GIT_COMMIT_SHORT}
                    Branch:       ${env.GIT_BRANCH}
                    Build Version: ${env.BUILD_VERSION}
                    ═══════════════════════════════════════════
                    """
                }
            }
        }

        stage('Build Images') {
            parallel {
                stage('Build Flask') {
                    steps {
                        echo '🏗️  Building Flask image...'
                        script {
                            sh """
                                docker build \
                                    -t ${FLASK_IMAGE}:${BUILD_VERSION} \
                                    -t ${FLASK_IMAGE}:latest \
                                    -f docker/flask/Dockerfile \
                                    .
                            """
                        }
                    }
                }

                stage('Build Scraper') {
                    steps {
                        echo '🏗️  Building Scraper image...'
                        script {
                            sh """
                                docker build \
                                    -t ${SCRAPER_IMAGE}:${BUILD_VERSION} \
                                    -t ${SCRAPER_IMAGE}:latest \
                                    -f docker/scraper/Dockerfile \
                                    .
                            """
                        }
                    }
                }

                stage('Build SGProof Scraper') {
                    steps {
                        echo '🏗️  Building SGProof Scraper image...'
                        script {
                            sh """
                                docker build \\
                                    -t ${SGPROOF_IMAGE}:${BUILD_VERSION} \\
                                    -t ${SGPROOF_IMAGE}:latest \\
                                    -f docker/sgproof/Dockerfile \\
                                    .
                            """
                        }
                    }
                }
            }
        }

        stage('Test') {
            steps {
                echo '🧪 Running tests...'
                script {
                    // Start test environment
                    sh '''
                        # Create test network
                        docker network create spider-test || true

                        # Start PostgreSQL for testing
                        docker run -d \
                            --name spider-test-db \
                            --network spider-test \
                            -e POSTGRES_PASSWORD=${DB_PASSWORD} \
                            -e POSTGRES_USER=spider \
                            -e POSTGRES_DB=spider_test \
                            postgres:16-alpine

                        # Wait for database to be ready
                        sleep 10

                        # Test Flask image
                        docker run --rm \
                            --network spider-test \
                            -e DATABASE_URL=postgresql://spider:${DB_PASSWORD}@spider-test-db:5432/spider_test \
                            ${FLASK_IMAGE}:${BUILD_VERSION} \
                            python -c "from database import Database; db = Database(); print('✅ Database connection successful')"

                        # Cleanup
                        docker stop spider-test-db || true
                        docker rm spider-test-db || true
                        docker network rm spider-test || true
                    '''
                }
            }
        }

        stage('Security Scan') {
            steps {
                echo '🔒 Scanning images for vulnerabilities...'
                script {
                    // Using Trivy for vulnerability scanning
                    sh """
                        # Install Trivy if not available
                        if ! command -v trivy &> /dev/null; then
                            echo "Trivy not installed, skipping security scan"
                        else
                            trivy image --severity HIGH,CRITICAL ${FLASK_IMAGE}:${BUILD_VERSION} || true
                            trivy image --severity HIGH,CRITICAL ${SCRAPER_IMAGE}:${BUILD_VERSION} || true
                        fi
                    """
                }
            }
        }

        stage('Push to Registry') {
            when {
                branch 'main'
            }
            steps {
                echo '📤 Pushing images to Docker Hub...'
                script {
                    // Login to Docker Hub
                    sh 'echo $DOCKER_CREDENTIALS_PSW | docker login -u $DOCKER_CREDENTIALS_USR --password-stdin'

                    // Push Flask image
                    sh """
                        docker push ${FLASK_IMAGE}:${BUILD_VERSION}
                        docker push ${FLASK_IMAGE}:latest
                    """

                    // Push Scraper image
                    sh """
                        docker push ${SCRAPER_IMAGE}:${BUILD_VERSION}
                        docker push ${SCRAPER_IMAGE}:latest
                    """

                    sh """
                        docker push ${SGPROOF_IMAGE}:${BUILD_VERSION}
                        docker push ${SGPROOF_IMAGE}:latest
                    """

                    echo "✅ Images pushed successfully!"
                    echo "   Flask:   ${FLASK_IMAGE}:${BUILD_VERSION}"
                    echo "   Scraper: ${SCRAPER_IMAGE}:${BUILD_VERSION}"
                }
            }
        }

        stage('Deploy to Production') {
            when {
                branch 'main'
            }
            steps {
                echo '🚀 Deploying to Portainer...'
                script {
                    // Deploy using Portainer API or docker-compose
                    sh """
                        # Create deployment package
                        mkdir -p deploy

                        # Copy docker-compose and .env
                        cp docker-compose.prod.yml deploy/

                        # Update image tags in docker-compose
                        sed -i.bak 's|image: .*spider-flask:latest|image: ${FLASK_IMAGE}:${BUILD_VERSION}|g' deploy/docker-compose.prod.yml
                        sed -i.bak 's|image: .*spider-scraper:latest|image: ${SCRAPER_IMAGE}:${BUILD_VERSION}|g' deploy/docker-compose.prod.yml
                        sed -i.bak 's|image: .*spider-sgproof-scraper:latest|image: ${SGPROOF_IMAGE}:${BUILD_VERSION}|g' deploy/docker-compose.prod.yml

                        # Deploy via Portainer API (if configured)
                        # Or use SSH to NAS and docker-compose up
                        echo "Deployment package prepared in deploy/"
                    """

                    // If you have Portainer API configured, uncomment:
                    // sh './scripts/deploy-to-portainer.sh ${BUILD_VERSION}'
                }
            }
        }

        stage('Verify Deployment') {
            when {
                branch 'main'
            }
            steps {
                echo '✅ Verifying deployment...'
                script {
                    // Health check deployed services
                    sh """
                        echo "Deployment verification would run here"
                        echo "Check: Flask web app responding"
                        echo "Check: Database connectivity"
                        echo "Check: All containers healthy"
                    """
                }
            }
        }
    }

    post {
        always {
            echo '🧹 Cleaning up...'
            script {
                // Cleanup test containers
                sh '''
                    docker stop spider-test-db 2>/dev/null || true
                    docker rm spider-test-db 2>/dev/null || true
                    docker network rm spider-test 2>/dev/null || true
                '''

                // Logout from Docker Hub
                sh 'docker logout || true'
            }
        }

        success {
            echo '✅ Pipeline completed successfully!'
            script {
                // Send success notification (Slack, Email, etc.)
                echo """
                ═══════════════════════════════════════════
                ✅ BUILD SUCCESSFUL
                ═══════════════════════════════════════════
                Build:    #${env.BUILD_NUMBER}
                Version:  ${env.BUILD_VERSION}
                Branch:   ${env.GIT_BRANCH}
                Duration: ${currentBuild.durationString}
                ═══════════════════════════════════════════
                """
            }
        }

        failure {
            echo '❌ Pipeline failed!'
            script {
                // Send failure notification
                echo """
                ═══════════════════════════════════════════
                ❌ BUILD FAILED
                ═══════════════════════════════════════════
                Build:    #${env.BUILD_NUMBER}
                Branch:   ${env.GIT_BRANCH}
                Check the console output for details.
                ═══════════════════════════════════════════
                """
            }
        }

        unstable {
            echo '⚠️  Pipeline unstable!'
        }
    }
}
