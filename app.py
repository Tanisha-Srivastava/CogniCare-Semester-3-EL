from flask import Flask, render_template, request, jsonify
import cv2
from deepface import DeepFace
import numpy as np
import sqlite3
import pickle
import time

app = Flask(__name__)

# Database setup
conn = sqlite3.connect('face_recognition.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    vector BLOB NOT NULL
);
''')
conn.commit()

# Load known faces from the database
known_faces = {}
cursor.execute("SELECT id, name, vector FROM persons")
for person_id, name, vector_blob in cursor.fetchall():
    embedding = pickle.loads(vector_blob)
    known_faces[person_id] = (name, embedding)

new_face_id = None
new_embedding = None

# Route for the main page
@app.route('/')
def index():
    return render_template('index.html')

# Route to start recognition
@app.route('/start_recognition', methods=['POST'])
def start_recognition():
    global new_face_id, new_embedding
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process the frame and check if the person is new
        embedding = get_face_embedding(frame)
        
        if embedding is not None:
            found_match = False
            for person_id, (name, stored_embedding) in known_faces.items():
                distance = np.linalg.norm(np.array(stored_embedding) - np.array(embedding))
                if distance < 0.7:  # Use the threshold for matching
                    cap.release()
                    cv2.destroyAllWindows()
                    return jsonify({'recognized': True, 'name': name})  # Send the recognized name

            if not found_match:
                # New face detected
                new_face_id = len(known_faces) + 1
                new_embedding = embedding  # Store the embedding for later
                cap.release()
                cv2.destroyAllWindows()
                return jsonify({'new_face_detected': True, 'id': new_face_id})
        
        cv2.imshow('Face Recognition', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return jsonify({'new_face_detected': False})

# Route to submit the new person's name
@app.route('/submit_name', methods=['POST'])
def submit_name():
    global new_face_id, new_embedding, known_faces

    if new_face_id is None or new_embedding is None:
        return jsonify({'error': 'No new face detected'}), 400

    name = request.form['name']
    vector_blob = pickle.dumps(new_embedding)
    cursor.execute("INSERT INTO persons (id, name, vector) VALUES (?, ?, ?)", (new_face_id, name, vector_blob))
    conn.commit()

    # Update the in-memory known faces
    known_faces[new_face_id] = (name, new_embedding)

    # Reset new_face_id and new_embedding
    new_face_id = None
    new_embedding = None
    return jsonify({'success': True})

# Helper function to get face embeddings
def get_face_embedding(frame):
    try:
        embeddings = DeepFace.represent(frame, model_name='VGG-Face', enforce_detection=True)
        return embeddings[0]['embedding'] if embeddings else None
    except Exception as e:
        return None



if __name__ == '__main__':
    app.run(debug=True)