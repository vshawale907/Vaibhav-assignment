# Testing

Docker and Minikube are not available in the environment where this code was written, so each section below shows the exact command and marks the output as TODO for you to run and paste.

---

## Auth enforcement

Connect without credentials and confirm the command is rejected.

```
kubectl exec -n flask-mongo -it mongo-0 -- mongosh
```

Inside the shell:

```
use flask_db
db.data.find()
```

TODO: paste output (expected: MongoServerError: command find requires authentication)

Connect as the app user and confirm it works:

```
kubectl exec -n flask-mongo -it mongo-0 -- \
  mongosh flask_db -u flaskuser -p flaskpass --authenticationDatabase flask_db
```

TODO: paste output (expected: connection accepted, db.data.find() returns cursor)

Connect as root and confirm it cannot write to flask_db with the app user role:

```
kubectl exec -n flask-mongo -it mongo-0 -- \
  mongosh admin -u root -p rootpass --eval \
  "db.getSiblingDB('flask_db').getUser('flaskuser')"
```

TODO: paste output showing roles: [{ role: 'readWrite', db: 'flask_db' }]

---

## PV/PVC binding

```
kubectl get pv
kubectl get pvc -n flask-mongo
```

TODO: paste output showing mongo-pv Bound to mongo-data-mongo-0

---

## POST then GET through the API

Get the node IP and run a write followed by a read.

```
NODE_IP=$(minikube ip)

curl -X POST http://$NODE_IP:30080/data \
  -H "Content-Type: application/json" \
  -d '{"name":"alice","score":99}'
```

TODO: paste output (expected: {"status": "Data inserted"} with 201)

```
curl http://$NODE_IP:30080/data
```

TODO: paste output (expected: [{"name":"alice","score":99}])

Invalid JSON returns 400:

```
curl -X POST http://$NODE_IP:30080/data \
  -H "Content-Type: application/json" \
  -d 'not json'
```

TODO: paste output (expected: {"error":"invalid json"} with 400)

---

## Persistence after pod deletion

```
kubectl delete pod -n flask-mongo mongo-0
kubectl get pods -n flask-mongo -w
```

TODO: paste output showing mongo-0 terminating and then Running again

```
curl http://$NODE_IP:30080/data
```

TODO: paste output showing the same document from before the deletion

---

## HPA under load

Open three terminals.

Terminal 1:

```
kubectl get hpa -n flask-mongo -w
```

Terminal 2:

```
kubectl top pods -n flask-mongo
```

Terminal 3: run the load script inside a temporary pod so the traffic comes from inside the cluster.

```
kubectl run load --image=busybox -n flask-mongo --restart=Never -it --rm -- \
  sh -c 'while true; do wget -qO- http://flask.flask-mongo.svc.cluster.local/; done'
```

TODO: paste HPA output showing REPLICAS going from 2 toward 5 as CPU climbs above 70%

Stop the load pod with Ctrl-C. After the cool-down period (default 5 minutes):

```
kubectl get hpa -n flask-mongo
```

TODO: paste output showing REPLICAS back at 2

