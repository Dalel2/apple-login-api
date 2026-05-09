from core_3 import app
from core import logger

if __name__ == "__main__":
    logger.info("Démarrage du serveur Flask...")
    app.run(host="0.0.0.0", port=8000, debug=True)