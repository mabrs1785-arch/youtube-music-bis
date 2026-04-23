#!/usr/bin/env python3
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â       HELPER â GÃ©nÃ©ration du Refresh Token YouTube OAuth        â
â       Ã exÃ©cuter UNE SEULE FOIS en local sur ton PC             â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

PrÃ©-requis :
  pip install google-auth-oauthlib

Usage :
  1. CrÃ©e un projet Google Cloud
  2. Active l'API YouTube Data v3
  3. CrÃ©e des identifiants OAuth 2.0 de type "Application de bureau"
  4. TÃ©lÃ©charge le fichier client_secrets.json
  5. Lance ce script : python get_refresh_token.py
  6. Suis les instructions dans le terminal
  7. Copie le refresh_token dans tes secrets GitHub

Important : NE JAMAIS committer client_secrets.json dans le repo !
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("â Module manquant. Lance : pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CLIENT_SECRETS_FILE = "client_secrets.json"


def main():
    print("=" * 60)
    print("  GÃ©nÃ©rateur de Refresh Token YouTube OAuth 2.0")
    print("  (YouTube Music Bot)")
    print("=" * 60)
    print()

    if not Path(CLIENT_SECRETS_FILE).exists():
        print(f"â Fichier '{CLIENT_SECRETS_FILE}' introuvable.")
        print()
        print("  Comment l'obtenir :")
        print("  1. Va sur https://console.cloud.google.com/")
        print("  2. SÃ©lectionne ou crÃ©e ton projet")
        print("  3. Menu â APIs & Services â Identifiants")
        print("  4. CrÃ©er des identifiants â ID client OAuth")
        print("  5. Type : Application de bureau")
        print("  6. TÃ©lÃ©charge le JSON et renomme-le 'client_secrets.json'")
        print("  7. Place-le dans le mÃªme dossier que ce script")
        print()
        sys.exit(1)

    print("ð Instructions :")
    print("  1. Un navigateur va s'ouvrir")
    print("  2. Connecte-toi avec le compte Google propriÃ©taire de la chaÃ®ne")
    print("  3. Autorise l'accÃ¨s YouTube")
    print("  4. Reviens ici â le refresh token sera affichÃ©")
    print()
    input("Appuie sur EntrÃ©e pour continuer...")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
    )

    creds = flow.run_local_server(
        port=8080,
        prompt="consent",
        access_type="offline",
    )

    print()
    print("â Authentification rÃ©ussie !")
    print()
    print("â" * 60)
    print("COPIE CES VALEURS DANS TES SECRETS GITHUB :")
    print("â" * 60)
    print()

    with open(CLIENT_SECRETS_FILE) as f:
        secrets = json.load(f)
    client_info = secrets.get("installed") or secrets.get("web") or {}

    print(f"  YOUTUBE_CLIENT_ID      = {client_info.get('client_id', 'N/A')}")
    print(f"  YOUTUBE_CLIENT_SECRET  = {client_info.get('client_secret', 'N/A')}")
    print(f"  YOUTUBE_REFRESH_TOKEN  = {creds.refresh_token}")
    print()
    print("â" * 60)
    print()
    print("â ï¸  NE JAMAIS committer ces valeurs dans le repo !")
    print("   Utilise les Secrets GitHub (Settings â Secrets â Actions)")
    print()

    save = input("Sauvegarder dans 'tokens.local.json' (ne pas committer) ? [o/N] ")
    if save.lower() in ("o", "oui", "y", "yes"):
        data = {
            "YOUTUBE_CLIENT_ID":     client_info.get("client_id"),
            "YOUTUBE_CLIENT_SECRET": client_info.get("client_secret"),
            "YOUTUBE_REFRESH_TOKEN": creds.refresh_token,
        }
        with open("tokens.local.json", "w") as f:
            json.dump(data, f, indent=2)
        print("ð¾ Tokens sauvegardÃ©s dans 'tokens.local.json'")
        print("   Ce fichier est dans .gitignore â il ne sera pas commitÃ©.")


if __name__ == "__main__":
    main()
