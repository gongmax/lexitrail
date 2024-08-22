apiVersion: apps/v1
kind: Deployment
metadata:
  name: lexitrail-ui-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lexitrail-ui
  template:
    metadata:
      labels:
        app: lexitrail-ui
    spec:
      containers:
      - name: lexitrail-ui
        image: gcr.io/${project_id}/${container_name}:latest
        ports:
        - containerPort: 3000

---
apiVersion: v1
kind: Service
metadata:
  name: lexitrail-ui-service
spec:
  selector:
    app: lexitrail-ui
  ports:
  - protocol: TCP
    port: 80
    targetPort: 3000
  type: LoadBalancer
