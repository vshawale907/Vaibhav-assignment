#!/bin/sh
NODE_IP=${1:-$(minikube ip)}
URL="http://${NODE_IP}:30080"
while true; do
  wget -qO- "$URL/" > /dev/null || true
  wget -qO- --post-data='{"load":"test"}' --header='Content-Type:application/json' "$URL/data" > /dev/null || true
done

