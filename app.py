import datetime
import random
from flask import Flask, render_template, request, jsonify, session, redirect, flash
import cv2
import numpy as np
import sqlite3
import pickle
import time
from deepface import DeepFace

import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Initialize an in-memory cache for known faces
known_faces = {}

# Initialize global variables for new face handling
new_face_id = None
new_embedding = None
db_path = 'cognicare_face_recognition.db'
conn = sqlite3.connect(db_path, check_same_thread=False)

cursor = conn.cursor()

# Database setup


# Ensure database and tables exist
def init_db():
    conn = sqlite3.connect(db_path, check_same_thread=False)

    cursor = conn.cursor()

    # Create table schema for persons
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS persons (
        id INTEGER,
        patname TEXT NOT NULL,
        caregiver TEXT NOT NULL,
        name TEXT NOT NULL,
        vector BLOB NOT NULL,
        PRIMARY KEY (id, name)
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS medication_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medication_name TEXT NOT NULL,
    time TEXT NOT NULL,
    dosage TEXT NOT NULL,
    notes TEXT
    );
    ''')
    

    # Create places table schema
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS places (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        place_name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        FOREIGN KEY (patient_id) REFERENCES persons(id)
    );
    ''')

    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Hangman game words with hints
words_with_hints = {
    "sun": "What shines brightly in the sky.",
    "tree": "Tall plant with leaves and branches.",
    "bird": "Animal that can fly.",
    "cat": "Small, furry animal that purrs.",
    "dog": "Loyal animal that barks."
}

@app.route('/hangman_reset', methods=['POST'])
def hangman_reset():
    # Randomly choose a word and its hint
    word, hint = random.choice(list(words_with_hints.items()))
    session['word'] = word
    session['hint'] = hint  # Store the hint in the session
    session['guessed_letters'] = []
    session['attempts'] = 6
    return jsonify({
        'message': 'Game reset!',
        'word_display': display_word(session['word'], session['guessed_letters']),
        'hint': session['hint'],  # Include the hint in the response
        'attempts': session['attempts']
    })

@app.route('/hangman')
def hangman():
    # Randomly choose a word and its hint
    word, hint = random.choice(list(words_with_hints.items()))  # Get a random word-hint pair
    session['word'] = word  # Store the word in the session
    session['hint'] = hint  # Store the hint in the session
    session['guessed_letters'] = []
    session['attempts'] = 6

    # Pass the initial state to the template
    return render_template(
        'hangman.html',
        word_display="_ " * len(word),  # Initial masked word
        hint=hint,  # Pass the hint to the template
        attempts=session['attempts']
    )

@app.route('/hangman_guess', methods=['POST'])
def hangman_guess():
    letter = request.json.get('letter', '').lower()

    if 'word' not in session:
        return jsonify({'error': 'Game not initialized'}), 400

    word = session['word']
    guessed_letters = session.get('guessed_letters', [])
    attempts = session['attempts']

    if letter in guessed_letters:
        return jsonify({
            'message': 'Already guessed this letter.',
            'status': 'repeat',
            'word_display': display_word(word, guessed_letters),
            'attempts': attempts
        })

    guessed_letters.append(letter)
    session['guessed_letters'] = guessed_letters

    if letter in word:
        if all(char in guessed_letters for char in word):
            return jsonify({
                'message': 'Congratulations! You guessed the word.',
                'status': 'win',
                'word': word,
                'word_display': display_word(word, guessed_letters),
                'attempts': attempts
            })
        return jsonify({
            'message': 'Correct!',
            'status': 'continue',
            'word_display': display_word(word, guessed_letters),
            'attempts': attempts
        })
    else:
        session['attempts'] -= 1
        attempts = session['attempts']
        if attempts == 0:
            return jsonify({
                'message': f'Game Over! The word was {word}.',
                'status': 'lose',
                'word': word,
                'word_display': display_word(word, guessed_letters),
                'attempts': attempts
            })
        return jsonify({
            'message': 'Incorrect.',
            'status': 'continue',
            'word_display': display_word(word, guessed_letters),
            'attempts': attempts
        })

def display_word(word, guessed_letters):
    return " ".join([letter if letter in guessed_letters else "_" for letter in word])

@app.route('/patient_page')
def patient_page():
    if 'patname' in session and 'patient_id' in session:
        return render_template('patient_page.html', name=session['patname'], patient_id=session['patient_id'])
    return redirect('/')  # Redirect to home if session is missing


@app.route('/')
def index():
    return render_template('select_role.html')

@app.route('/patient_signup')
def patient_signup():
    return render_template('patient_signup.html')

@app.route('/signup', methods=['POST'])
def signup():
    patient_id = request.form.get('patient_id')
    patname = request.form.get('patname')  # Use patname for consistency
    caregiver = request.form.get('caregiver')  # Ensure caregiver is provided

    # Check if the patient_id already exists
    conn = sqlite3.connect(db_path, check_same_thread=False)

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM persons WHERE id = ?", (patient_id,))
    existing_patient = cursor.fetchone()

    if existing_patient:
        flash("Error: Patient ID already exists. Please use a different ID.", "error")
        return redirect('/patient_signup')

    # Ensure caregiver information is provided
    if not caregiver:
        flash("Error: Caregiver information is required.", "error")
        return redirect('/patient_signup')

    # Save the patient info in the database
    cursor.execute("INSERT INTO persons (id, patname, caregiver, name, vector) VALUES (?, ?, ?, ?, ?)", 
                   (patient_id, patname, caregiver, '', pickle.dumps([])))  # No face added yet
    conn.commit()

    # Store the patient ID and caregiver in the session
    session['patient_id'] = patient_id
    session['patname'] = patname
    session['caregiver'] = caregiver  # Store caregiver in session for future use

    return render_template('patient_page.html', name=patname, patient_id=patient_id)

@app.route('/login', methods=['POST'])
def login():
    patient_id = request.form['patient_id']
    patname = request.form['patname']  # Use patname for consistency

    # Check if patient_id and patname exist in the database
    conn = sqlite3.connect(db_path, check_same_thread=False)

    cursor = conn.cursor()
    cursor.execute("SELECT id, patname, caregiver FROM persons WHERE id = ? AND patname = ?", (patient_id, patname))
    existing_patient = cursor.fetchone()

    if not existing_patient:
        flash("Error: Patient ID and name do not match. Please try again or sign up first.", "error")
        return redirect('/patient_signup')

    session['patient_id'] = existing_patient[0]
    session['patname'] = existing_patient[1]
    session['caregiver'] = existing_patient[2]  # Store caregiver in session for future use

    return render_template('patient_page.html', name=existing_patient[1], patient_id=existing_patient[0])

@app.route('/start_recognition', methods=['POST'])
def start_recognition():
    global new_face_id, new_embedding
    cap = cv2.VideoCapture(0)
    start_time = time.time()  # Record the starting time
    face_detected = False  # Track if any face is detected

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process the frame and check if the person is new
        embedding = get_face_embedding(frame)
        if embedding is not None:
            face_detected = True  # Mark that a face has been detected
            found_match = False
            # Match against known faces for the current patient
            current_patient_id = session.get('patient_id')  # Get the patient ID from the session

            # Fetch known faces from the database for the current patient
            if current_patient_id not in known_faces:
                known_faces[current_patient_id] = []
                cursor.execute("SELECT name, vector FROM persons WHERE id = ?", (current_patient_id,))
                rows = cursor.fetchall()
                for name, vector_blob in rows:
                    stored_embedding = pickle.loads(vector_blob)
                    if isinstance(stored_embedding, list) and len(stored_embedding) == len(embedding):
                        known_faces[current_patient_id].append((name, stored_embedding))

            for name, stored_embedding in known_faces[current_patient_id]:
                # Ensure shapes match before computing the distance
                if len(stored_embedding) == len(embedding):
                    distance = np.linalg.norm(np.array(stored_embedding) - np.array(embedding))
                    if distance < 0.7:  # Use the threshold for matching
                        cap.release()
                        cv2.destroyAllWindows()
                        return jsonify({'recognized': True, 'name': name})  # Send the recognized name

            if not found_match:
                # New face detected
                new_face_id = current_patient_id
                new_embedding = embedding  # Store the embedding for later
                cap.release()
                cv2.destroyAllWindows()
                return jsonify({'new_face_detected': True, 'id': new_face_id})

        # Check if the timeout has been exceeded
        elapsed_time = time.time() - start_time
        if elapsed_time > 5:
            cap.release()
            cv2.destroyAllWindows()
            if not face_detected:
                return jsonify({'error': 'No face detected'})  # New response for no face detected
            return jsonify({'new_face_detected': True, 'timeout': True, 'id': session.get('patient_id')})

        cv2.imshow('Face Recognition', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return jsonify({'new_face_detected': False})

@app.route('/submit_name', methods=['POST'])
def submit_name():
    global new_face_id, new_embedding, known_faces

    if new_face_id is None or new_embedding is None:
        return jsonify({'error': 'No new face detected'}), 400

    # Get the name from the form submission
    name = request.form['name']

    # Serialize the embedding for database storage
    vector_blob = pickle.dumps(new_embedding)

    # Insert into the database with the associated patient ID
    cursor.execute("INSERT INTO persons (id, patname, caregiver, name, vector) VALUES (?, ?, ?, ?, ?)",
                   (new_face_id, session['patname'], session['caregiver'], name, vector_blob))
    conn.commit()

    # Update the in-memory known faces dictionary
    if new_face_id not in known_faces:
        known_faces[new_face_id] = []
    known_faces[new_face_id].append((name, new_embedding))

    # Reset the new face ID and embedding variables
    new_face_id = None
    new_embedding = None

    # Redirect back to patient page with updated info
    return render_template('patient_page.html', name=session['patname'], patient_id=session['patient_id'])

# Helper function to get face embeddings
def get_face_embedding(frame):
    try:
        embeddings = DeepFace.represent(frame, model_name='VGG-Face', enforce_detection=True)
        return embeddings[0]['embedding'] if embeddings else None
    except Exception:
        return None

@app.route('/caregiver_signup')
def caregiver_signup():
    return render_template('caregiver_signup.html', patients=None)

@app.route('/caregiver', methods=['POST'])
def caregiver():
    caregiver_name = request.form['name']
    patient_id = request.form['patient_id']

    # Check if the caregiver is associated with the patient
    conn = sqlite3.connect(db_path, check_same_thread=False)

    cursor = conn.cursor()
    cursor.execute("SELECT caregiver FROM persons WHERE id = ?", (patient_id,))
    patient_data = cursor.fetchone()

    if not patient_data:
        flash("Error: Patient ID not found. Please check the ID and try again.", "error")
        return redirect('/caregiver_signup')

    stored_caregiver = patient_data[0]

    # Verify if the caregiver name matches
    if caregiver_name != stored_caregiver:
        flash("Error: The caregiver name does not match the given Patient ID.", "error")
        return redirect('/caregiver_signup')

    # Fetch all names associated with the patient_id for the caregiver dashboard
    cursor.execute("SELECT name FROM persons WHERE id = ?", (patient_id,))
    patients = cursor.fetchall()

    # Fetch the saved places associated with the patient_id
    cursor.execute("SELECT place_name, latitude, longitude FROM places WHERE patient_id = ?", (patient_id,))
    saved_places = cursor.fetchall()

    # Render the caregiver dashboard page with the associated names and places
    return render_template('caregiver_page.html', patients=patients, saved_places=saved_places)

@app.route('/medication')
def medication_reminders():
    cursor.execute("SELECT * FROM medication_reminders ORDER BY time ASC")
    reminders = cursor.fetchall()
    return render_template('medication.html', reminders=reminders)

# Route to add a new medication reminder
@app.route('/add_reminder', methods=['POST'])
def add_reminder():
    medication_name = request.form['medication_name']
    time = request.form['time']
    dosage = request.form['dosage']
    notes = request.form['notes']

    cursor.execute(
        "INSERT INTO medication_reminders (medication_name, time, dosage, notes) VALUES (?, ?, ?, ?)",
        (medication_name, time, dosage, notes)
    )
    conn.commit()
    return jsonify({'success': True, 'message': 'Reminder added successfully!'})

# Route to delete a medication reminder
@app.route('/delete_reminder/<int:reminder_id>', methods=['POST'])
def delete_reminder(reminder_id):
    cursor.execute("DELETE FROM medication_reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    return jsonify({'success': True, 'message': 'Reminder deleted successfully!'})

@app.route('/check_reminders', methods=['GET'])
def check_reminders():
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    cursor.execute("SELECT * FROM medication_reminders WHERE time = ?", (current_time,))
    due_reminders = cursor.fetchall()

    if due_reminders:
        reminders = [
            {
                'medication_name': reminder[1],
                'time': reminder[2],
                'dosage': reminder[3],
                'notes': reminder[4]
            }
            for reminder in due_reminders
        ]
        return jsonify({'due_reminders': reminders})
    return jsonify({'due_reminders': []})

@app.route('/navigation', methods=['GET', 'POST'])
def navigation():
    patient_id = session.get('patient_id')
    if not patient_id:
        return redirect('/')  # Redirect to login if not logged in

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if request.method == 'POST':
        # Save a new place
        place_name = request.form['place_name']
        latitude = request.form['latitude']
        longitude = request.form['longitude']

        cursor.execute("INSERT INTO places (patient_id, place_name, latitude, longitude) VALUES (?, ?, ?, ?)",
                       (patient_id, place_name, latitude, longitude))
        conn.commit()
        return jsonify({'status': 'success'})

    # Fetch all saved places for the logged-in patient
    cursor.execute("SELECT place_name, latitude, longitude FROM places WHERE patient_id = ?", (patient_id,))
    places = cursor.fetchall()
    conn.close()

    return render_template('navigation.html', places=places)

@app.route('/api/places', methods=['GET'])
def get_places():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'Not logged in'}), 401

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT place_name, latitude, longitude FROM places WHERE patient_id = ?", (patient_id,))
    places = cursor.fetchall()
    conn.close()

    return jsonify([{'name': p[0], 'lat': p[1], 'lng': p[2]} for p in places])

@app.route('/api/route', methods=['POST'])
def calculate_route():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'Not logged in'}), 401

    source = request.json.get('source')
    destination = request.json.get('destination')

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude FROM places WHERE patient_id = ? AND place_name = ?",
                   (patient_id, source))
    source_coords = cursor.fetchone()

    cursor.execute("SELECT latitude, longitude FROM places WHERE patient_id = ? AND place_name = ?",
                   (patient_id, destination))
    destination_coords = cursor.fetchone()
    conn.close()

    if not source_coords or not destination_coords:
        return jsonify({'error': 'Invalid source or destination'}), 400

    return jsonify({'source': {'lat': source_coords[0], 'lng': source_coords[1]},
                    'destination': {'lat': destination_coords[0], 'lng': destination_coords[1]}})

if __name__ == '__main__':
    app.run(debug=True)
