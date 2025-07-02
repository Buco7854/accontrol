#!/bin/sh

# Stoppe le script immédiatement si une commande échoue
set -e

# Exécute le script d'initialisation de la base de données
echo "Vérification de la base de données..."
python init_db.py

# Affiche un message et exécute ensuite la commande passée au script
# "$@" est une variable spéciale qui contient tous les arguments passés au script
# (par exemple, "gunicorn --bind 0.0.0.0:5000 app:app")
echo "Lancement du processus principal..."
exec "$@"