from flask import Flask, request, jsonify
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from datetime import datetime
import os

app = Flask(__name__)

_db = os.environ.get("MONGO_DB", "flask_db")
client = MongoClient(
    host=os.environ.get("MONGO_HOST", "localhost"),
    port=27017,
    username=os.environ.get("MONGO_USER"),
    password=os.environ.get("MONGO_PASSWORD"),
    authSource=_db,
)
collection = client[_db].data


@app.route("/")
def index():
    return f"Welcome to the Flask app! The current time is: {datetime.now()}"


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/data", methods=["GET", "POST"])
def data():
    if request.method == "POST":
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "invalid json"}), 400
        try:
            collection.insert_one(body)
        except PyMongoError as e:
            return jsonify({"error": str(e)}), 503
        return jsonify({"status": "Data inserted"}), 201
    try:
        docs = list(collection.find({}, {"_id": 0}))
    except PyMongoError as e:
        return jsonify({"error": str(e)}), 503
    return jsonify(docs), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
