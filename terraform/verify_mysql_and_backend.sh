#!/bin/bash

# Exit script on any error
set -e

# Parameters
CLUSTER_NAME=lexitrail-cluster
REGION=us-central1
MYSQL_NAMESPACE=mysql
BACKEND_NAMESPACE=backend
UI_NAMESPACE=default  # Assuming UI is in the default namespace
DBNAME=lexitraildb
BACKEND_SERVICE_NAME=lexitrail-backend-service
BACKEND_PORT=5000  # The port your Flask app listens on
BACKEND_ROUTE=/wordsets
UI_SERVICE_NAME=lexitrail-ui-service
UI_ROUTE=/

# Load environment variables from the parent directory's .env file
if [ -f ../.env ]; then
    echo "Loading environment variables from ../.env file..."
    export $(grep -v '^#' ../.env | xargs)
else
    echo "Error: .env file not found in the parent directory!"
    exit 1
fi

# Check if db_root_password is set
if [ -z "$DB_ROOT_PASSWORD" ]; then
    echo "Error: DB_ROOT_PASSWORD not set in the .env file!"
    exit 1
fi

# Authenticate with the GKE cluster
echo "Authenticating with the GKE cluster..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION"

# ========== MySQL Verification using MySQL Pod ==========

# Get the MySQL pod name
MYSQL_POD=$(kubectl get pods -n "$MYSQL_NAMESPACE" -l app=mysql -o jsonpath='{.items[0].metadata.name}')

echo "Found MySQL pod: $MYSQL_POD"

# Verify that the database exists using the MySQL pod
echo "Checking for databases from MySQL pod..."
kubectl exec -n "$MYSQL_NAMESPACE" "$MYSQL_POD" -- mysql -u root -p"$DB_ROOT_PASSWORD" -e "SHOW DATABASES;"

# Verify tables in the database
echo "Checking for tables in $DBNAME from MySQL pod..."
kubectl exec -n "$MYSQL_NAMESPACE" "$MYSQL_POD" -- mysql -u root -p"$DB_ROOT_PASSWORD" -e "USE $DBNAME; SHOW TABLES;"

# Verify that data exists in the words table
echo "Checking data in words table in $DBNAME from MySQL pod..."
kubectl exec -n "$MYSQL_NAMESPACE" "$MYSQL_POD" -- mysql -u root -p"$DB_ROOT_PASSWORD" -e "USE $DBNAME; SELECT * FROM words LIMIT 55;"

# ========== Flask Backend Verification using Local Port Forwarding ==========

echo "Setting up port forwarding for the Flask backend service..."

# Start kubectl port-forward in the background
kubectl port-forward svc/$BACKEND_SERVICE_NAME $BACKEND_PORT:$BACKEND_PORT -n $BACKEND_NAMESPACE &
PORT_FORWARD_PID=$!

# Wait a few seconds to ensure port forwarding is active
sleep 5

# Define the local URL for verification
BACKEND_URL="http://localhost:$BACKEND_PORT$BACKEND_ROUTE"

echo "Verifying the /wordsets route at $BACKEND_URL..."

# Make the request to the Flask backend service via localhost and capture the response
HTTP_RESPONSE=$(curl --write-out "%{http_code}" --silent --output /tmp/wordsets_response.json "$BACKEND_URL")
RESPONSE_BODY=$(cat /tmp/wordsets_response.json)

# Check if the HTTP response code is 200 (OK)
if [ "$HTTP_RESPONSE" -eq 200 ]; then
    echo "Flask backend /wordsets route responded successfully!"
    echo "Wordsets returned by the backend:"
    echo "$RESPONSE_BODY"
else
    echo "Error: Failed to verify Flask backend /wordsets route! HTTP response code: $HTTP_RESPONSE"
    echo "Response body:"
    echo "$RESPONSE_BODY"
    # Stop the port forwarding before exiting
    kill $PORT_FORWARD_PID
    exit 1
fi

# Stop the port forwarding
kill $PORT_FORWARD_PID

# ========== UI Verification using LoadBalancer IP ==========

# Get the external IP address of the UI service
UI_IP=$(kubectl get svc -n "$UI_NAMESPACE" "$UI_SERVICE_NAME" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

if [ -z "$UI_IP" ]; then
    echo "Error: Unable to get external IP for the React UI service!"
    exit 1
fi

UI_URL="http://$UI_IP$UI_ROUTE"

echo "Verifying the React UI is accessible at $UI_URL..."

# Make the request to the React UI and capture the HTTP status code
UI_HTTP_RESPONSE=$(curl --write-out "%{http_code}" --silent --output /dev/null "$UI_URL")

# Check if the HTTP response code is 200 (OK)
if [ "$UI_HTTP_RESPONSE" -eq 200 ]; then
    echo "React UI is accessible and responded successfully!"
else
    echo "Error: Failed to verify React UI! HTTP response code: $UI_HTTP_RESPONSE"
    exit 1
fi

echo "All verifications completed successfully!"