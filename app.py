# app.py
import sqlite3
import os
from flask import Flask, jsonify, send_from_directory, g, request

app = Flask(__name__, static_folder='static', static_url_path='/static')

DATABASE = os.path.join('data', 'database.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- API Routes ---
@app.route('/api/splits', methods=['GET'])
def get_splits():
    cursor = get_db().cursor()
    splits_from_db = cursor.execute('SELECT id, name, label, url FROM splits ORDER BY label').fetchall()
    return jsonify([dict(row) for row in splits_from_db])

@app.route('/api/splits', methods=['POST'])
def add_split():
    new_split = request.get_json()
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("INSERT INTO splits (name, label, url) VALUES (?, ?, ?)", (new_split['name'], new_split['label'], new_split['url']))
        db.commit()
        new_split['id'] = cursor.lastrowid
        return jsonify(new_split), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Un split avec ce nom existe déjà."}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/splits/<int:split_id>', methods=['PUT'])
def update_split(split_id):
    data = request.get_json()
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("UPDATE splits SET name = ?, label = ?, url = ? WHERE id = ?", (data['name'], data['label'], data['url'], split_id))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": "Split non trouvé"}), 404
        return jsonify(data)
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/splits/<int:split_id>', methods=['DELETE'])
def delete_split(split_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM splits WHERE id = ?", (split_id,))
    db.commit()
    if cursor.rowcount == 0:
        return jsonify({"error": "Split non trouvé"}), 404
    return jsonify({"message": "Split supprimé avec succès"}), 200

# --- Frontend Routes ---
@app.route('/')
@app.route('/split/<path:path>')
@app.route('/manage')
def serve_spa(path=None):
    return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    # S'assure que le dossier de données existe avant de lancer
    if not os.path.exists('data'):
        print("Le dossier 'data' n'existe pas. Veuillez lancer 'python init_db.py' d'abord.")
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)
