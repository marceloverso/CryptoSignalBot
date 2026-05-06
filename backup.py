# ═══════════════════════════════════════════════════════════════
#  🤖 TRADEBOT v1.0 — backup.py
#  Backup del historial en GitHub. Idéntico al bot de apuestas.
# ═══════════════════════════════════════════════════════════════

import os, logging, shutil, subprocess
from config import HISTORIAL_F
from utils  import ahora_colombia

logger = logging.getLogger(__name__)

def backup_historial_github() -> bool:
    try:
        git_token = os.environ.get("GITHUB_TOKEN", "")
        git_repo  = os.environ.get("GITHUB_REPOSITORY", "")
        if not git_token or not git_repo:
            logger.info("📁 Backup GitHub: fuera de Actions")
            return False

        subprocess.run(["git","config","user.email","tradebot@github-actions"],
                       check=True, capture_output=True)
        subprocess.run(["git","config","user.name","TradeBot Actions"],
                       check=True, capture_output=True)

        shutil.copy(str(HISTORIAL_F), "historial_backup.json")

        result = subprocess.run(["git","diff","--quiet","historial_backup.json"],
                                capture_output=True)
        if result.returncode == 0:
            logger.info("📁 Backup: sin cambios")
            return True

        ahora_str = ahora_colombia().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git","add","historial_backup.json"],
                       check=True, capture_output=True)
        subprocess.run(["git","commit","-m",f"backup: trades {ahora_str} Colombia"],
                       check=True, capture_output=True)
        subprocess.run(["git","push"], check=True, capture_output=True)
        logger.info("✅ Backup commiteado en GitHub")
        return True

    except subprocess.CalledProcessError as e:
        logger.warning(f"⚠️ Backup git error: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Backup: {e}")
        return False
