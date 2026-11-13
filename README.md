# flask-mongodb-k8s

This is my submission for the Kubernetes intern assignment. It deploys a Flask REST API backed by an authenticated MongoDB instance on a local Minikube cluster. Flask runs as a Deployment with two replicas behind a NodePort Service. MongoDB runs as a StatefulSet with a PersistentVolume for data durability.

---

## Run locally (Part 1)

I created a virtual environment to keep the project's dependencies separate from the system Python installation. Without one, installing Flask here could break another project that needs a different version. It also makes the exact set of packages reproducible via requirements.txt.

```
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python app.py
```

The app reads `MONGO_HOST`, `MONGO_USER`, `MONGO_PASSWORD`, and `MONGO_DB` from the environment. When those are absent it falls back to localhost on port 27017 without authentication, which is enough to test the endpoints locally.

```
curl http://localhost:5000/
curl http://localhost:5000/health
curl -X POST http://localhost:5000/data -H "Content-Type: application/json" -d '{"name":"test"}'
curl http://localhost:5000/data
```

---

## Build and push the image

```
docker build -t your-dockerhub-username/flask-mongodb-app:latest .
docker login
docker push your-dockerhub-username/flask-mongodb-app:latest
```

Replace `your-dockerhub-username` in `k8s/flask-deployment.yaml` before deploying.

If you want to avoid a push, load the image directly into Minikube and set `imagePullPolicy: Never` on the container:

```
minikube image load your-dockerhub-username/flask-mongodb-app:latest
```

---

## Deploy on Minikube

```
minikube start --driver=docker --memory=4096 --cpus=2
minikube addons enable metrics-server
minikube ssh "sudo mkdir -p /data/mongo"

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/mongo-secret.yaml
kubectl apply -f k8s/mongo-init-configmap.yaml
kubectl apply -f k8s/mongo-pv.yaml
kubectl apply -f k8s/mongo-statefulset.yaml
kubectl apply -f k8s/mongo-service.yaml
kubectl apply -f k8s/flask-deployment.yaml
kubectl apply -f k8s/flask-service.yaml
kubectl apply -f k8s/flask-hpa.yaml
```

Wait until all pods are ready:

```
kubectl get pods -n flask-mongo -w
```

Access the app:

```
minikube service flask -n flask-mongo
```

Or via port-forward if the Docker driver does not expose NodePorts directly:

```
kubectl port-forward -n flask-mongo svc/flask 8080:80
curl http://localhost:8080/
```

The Secret contains dev-only placeholder values. A production deployment would use an external secret manager such as HashiCorp Vault or Kubernetes sealed-secrets so credentials never appear in the repository.

---

## How Flask reaches MongoDB (DNS)

Every pod in Kubernetes gets `/etc/resolv.conf` written by kubelet. It lists the CoreDNS ClusterIP as the nameserver and adds a `search` line with the namespace suffix:

```
nameserver 10.96.0.10
search flask-mongo.svc.cluster.local svc.cluster.local cluster.local
```

When Flask calls `MongoClient(host="mongo.flask-mongo.svc.cluster.local")`, the OS resolver sends a query to CoreDNS. CoreDNS looks up the Service named `mongo` in namespace `flask-mongo` and returns its record.

I used a headless Service (`clusterIP: None`). A normal ClusterIP Service returns a stable virtual IP that kube-proxy forwards to a pod. A headless Service skips the virtual IP and returns the pod IP directly in DNS. For a StatefulSet that is correct because each pod has a stable DNS name of its own:

```
mongo-0.mongo.flask-mongo.svc.cluster.local
```

That name stays the same even if the pod is rescheduled. I set `MONGO_HOST` in the Deployment to `mongo.flask-mongo.svc.cluster.local` rather than a pod IP because pod IPs change on restart while the Service name does not.

Verify from inside a Flask pod:

```
kubectl exec -n flask-mongo deploy/flask -- nslookup mongo.flask-mongo.svc.cluster.local
kubectl exec -n flask-mongo deploy/flask -- cat /etc/resolv.conf
```

---

## Requests and limits

`requests.cpu: 200m` and `requests.memory: 250Mi` are what the scheduler uses to place a pod on a node. They are guaranteed minimums; the node will not be oversubscribed below them.

`limits.cpu: 500m` caps the CPU. If a container tries to use more, the kernel throttles it back down but does not kill it. `limits.memory: 500Mi` is different: if the container's resident set exceeds this value the kernel OOM-kills the process and Kubernetes restarts the pod.

Because requests are set, the pods land in the Burstable QoS class. Kubernetes evicts BestEffort pods first, then Burstable, so the pods will survive mild node pressure.

The HPA computes the number of replicas as:

```
desiredReplicas = ceil(currentReplicas * currentUtilization / 70)
```

Utilization is actual CPU divided by `requests.cpu`. That means the 200m request is the denominator. If I had not set a request the HPA would report unknown and refuse to scale.

I picked 200m/250Mi because gunicorn with two workers sits well under that at idle, and 500m/500Mi gives enough headroom for a short burst without hitting the OOMKill threshold. The MongoDB cache is capped at 256 MB via `--wiredTigerCacheSizeGB 0.25` so the 500Mi memory limit is sufficient.

---

## Design choices and alternatives I rejected

I used a StatefulSet for MongoDB instead of a Deployment because StatefulSets give each pod a stable hostname and a dedicated PersistentVolumeClaim. A Deployment pod gets a random name on restart and shares storage, which is not safe for a database.

I used a headless Service for MongoDB so that Flask can address `mongo-0` by its stable DNS name. A NodePort or LoadBalancer for the database would expose it outside the cluster, which I wanted to avoid.

I pre-created a hostPath PersistentVolume and a `storageClassName: manual` in the volumeClaimTemplate so that the StatefulSet's auto-generated PVC `mongo-data-mongo-0` binds to it without needing a dynamic provisioner. In production I would use a StorageClass backed by the cloud provider's block storage.

I created a separate `flaskuser` with `readWrite` on `flask_db` only, initialised via a shell script in a ConfigMap. Flask authenticates as that user with `authSource=flask_db`. The root credentials are only used during init and never exposed to the Flask process.

I did not add an Ingress controller because a NodePort is enough for local testing and adding nginx-ingress would be extra infrastructure with no benefit for this scope. I did not set up a MongoDB replica set because it requires at least three nodes and a complex init sequence; a single authenticated instance is sufficient for the assignment.

I did not add Helm, Kustomize, a service mesh, or a monitoring stack. All of those are reasonable for a real deployment but would obscure the core concepts this assignment is testing.

---

## Testing

Full test commands and output are in `docs/testing.md`. That file covers: verifying that unauthenticated access to MongoDB is rejected, POST then GET through the Flask API, deleting `mongo-0` and confirming data persists, running `scripts/load.sh` and watching the HPA scale up and back down.

---

## Things to watch for

If the HPA shows `<unknown>` for CPU targets, metrics-server is not running yet. Run `minikube addons enable metrics-server` and wait about 60 seconds.

If a Flask pod stays in CrashLoopBackOff immediately after deploy, the image name in `flask-deployment.yaml` probably still has the placeholder username. Update it and run `kubectl rollout restart deployment/flask -n flask-mongo`.

The init script in the ConfigMap runs only once, when `/data/db` is empty. If you change the Secret values after the first start you must delete the PVC, delete the PV, re-create them, and redeploy the StatefulSet so MongoDB initialises from scratch with the new credentials.
