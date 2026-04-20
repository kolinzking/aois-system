#!/usr/bin/env bash
# Install Strimzi Kafka operator on the Hetzner k3s cluster.
# Run once. Idempotent.
set -euo pipefail

STRIMZI_VERSION="0.41.0"
NAMESPACE="kafka"

echo "=== Installing Strimzi ${STRIMZI_VERSION} ==="

# Create namespace
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Install Strimzi operator (CRDs + RBAC + Deployment)
kubectl apply -f "https://strimzi.io/install/latest?namespace=${NAMESPACE}" -n ${NAMESPACE}

# Wait for operator to be ready
echo "Waiting for Strimzi operator..."
kubectl rollout status deployment/strimzi-cluster-operator -n ${NAMESPACE} --timeout=120s

echo "Strimzi operator ready."
