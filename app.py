# app.py
import os
import sqlite3
import requests
from urllib.parse import urljoin, urlparse
from flask import Flask, jsonify, send_from_directory, g, request, Response, stream_with_context, render_template
from dotenv import load_dotenv

# Charge les variables d'environnement du fichier .env pour le développement local
load_dotenv()

# --- Configuration de l'Application ---
# Utilisation de la configuration exacte que vous avez fournie
app = Flask(__name__, static_folder='static', static_url_path='/static', template_folder="templates")

DATABASE = os.path.join('data', 'database.db')
# On lit la variable d'environnement. Si elle n'est pas définie, on utilise 'localhost:5000' par défaut.
BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'localhost')

# IMPORTANT pour le routage par sous-domaine.
# Flask a besoin de savoir sur quel domaine principal il opère.
app.config['SERVER_NAME'] = BASE_DOMAIN


# --- Fonctions de base de données (inchangées) ---
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


# --- Routes du Dashboard ---
# Ces routes servent le fichier HTML principal en y injectant la variable d'environnement
@app.route('/')
@app.route('/split/<path:path>')
@app.route('/manage')
def serve_spa(path=None):
    return render_template('index.html', base_domain=BASE_DOMAIN)


# --- Routes de l'API (pour récupérer les données, ajouter, etc.) ---
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
        cursor.execute("INSERT INTO splits (name, label, url) VALUES (?, ?, ?)",
                       (new_split.get('name'), new_split.get('label'), new_split.get('url')))
        db.commit()
        new_split['id'] = cursor.lastrowid
        return jsonify(new_split), 201
    except sqlite3.IntegrityError:
        db.rollback()
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
        cursor.execute("UPDATE splits SET name = ?, label = ?, url = ? WHERE id = ?",
                       (data.get('name'), data.get('label'), data.get('url'), split_id))
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


# --- Proxy par Sous-Domaine ---
@app.route('/', defaults={'path': ''}, subdomain='<split_name>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<path:path>', subdomain='<split_name>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_subdomain(split_name, path):
    db = get_db()
    split = db.execute('SELECT url FROM splits WHERE name = ?', (split_name,)).fetchone()
    if not split:
        return f"Sous-domaine '{split_name}' non trouvé.", 404

    base_target_url = split['url']
    target_url = urljoin(base_target_url, path)

    try:
        headers = {key: value for (key, value) in request.headers if key.lower() not in ['host', 'cookie']}
        headers['Host'] = urlparse(target_url).netloc

        resp = requests.request(
            method=request.method, url=target_url, headers=headers,
            data=request.get_data(), cookies=request.cookies,
            allow_redirects=False, timeout=10, stream=True
        )
    except requests.exceptions.RequestException as e:
        return f"Erreur du proxy pour {target_url}: {e}", 502

    excluded_headers = ['transfer-encoding', 'connection', 'content-length', 'content-encoding']
    response_headers = [(name, value) for (name, value) in resp.raw.headers.items() if
                        name.lower() not in excluded_headers]

    return Response(stream_with_context(resp.iter_content(chunk_size=1024)), resp.status_code, response_headers)


# --- Bloc de Développement ---
if __name__ == '__main__':
    if not os.path.exists('data'):
        print("Attention : Le dossier 'data' est manquant. Lancez 'python init_db.py' d'abord.")
    app.run(host='0.0.0.0', port=5000, debug=True)