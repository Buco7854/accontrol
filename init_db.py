# init_db.py
import sqlite3
import os

# Le chemin vers le répertoire de données
DATA_DIR = 'data'
DATABASE_PATH = os.path.join(DATA_DIR, 'database.db')

# Crée le répertoire 'data' s'il n'existe pas, sans causer d'erreur s'il existe déjà
os.makedirs(DATA_DIR, exist_ok=True)

# Connexion à la base de données (le fichier sera créé s'il n'existe pas)
connection = sqlite3.connect(DATABASE_PATH)

try:
    print(f"Vérification de la base de données et de la structure à '{DATABASE_PATH}'...")

    # Création du curseur pour exécuter des requêtes
    with connection:
        # On utilise "IF NOT EXISTS" pour créer la table seulement si elle est manquante.
        # C'est un script 100% non-destructif.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS splits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                url TEXT NOT NULL
            );
        """)

    print("Structure de la base de données vérifiée et prête.")

except sqlite3.Error as e:
    print(f"Une erreur est survenue lors de l'initialisation de la base de données : {e}")

finally:
    # Valide les changements (la création de la table, si elle a eu lieu) et ferme la connexion
    if connection:
        connection.commit()
        connection.close()
