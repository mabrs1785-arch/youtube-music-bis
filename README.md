# ðµ YouTube Music Bot â ChaÃ®ne Musique IA AutomatisÃ©e

Pipeline 100% autonome qui publie **un morceau de musique IA par jour** sur YouTube (et YouTube Music), sans aucune intervention manuelle aprÃ¨s le setup.

---

## Architecture

```
daily_music.py              â script principal (tout le pipeline)
.github/workflows/
  daily.yml                 â GitHub Actions (dÃ©clenchÃ© chaque jour Ã  14h UTC)
  token-monitor.yml         â VÃ©rifie la validitÃ© des tokens chaque lundi
requirements.txt            â dÃ©pendances Python
songs_done.json             â tracker des morceaux dÃ©jÃ  publiÃ©s (auto-commitÃ©)
get_refresh_token.py        â helper one-shot pour obtenir le token OAuth YouTube
```

### Pipeline en 6 Ã©tapes

1. **Google Gemini** â gÃ©nÃ¨re le concept (titre, paroles, genre tags, description YouTube)
2. **Suno API** â gÃ©nÃ¨re le morceau de musique complet (paroles + instrumental)
3. **Pillow** â gÃ©nÃ¨re la pochette d'album style electro/moderne (1920Ã1080)
4. **FFmpeg** â assemble la vidÃ©o (image fixe + audio)
5. **Pillow** â gÃ©nÃ¨re la miniature YouTube (1280Ã720)
6. **YouTube API v3** â uploade la vidÃ©o avec `categoryId: 10` (Musique) â visible sur YouTube Music

---

Consultez le README complet dans le fichier pour le setup dÃ©taillÃ©, le troubleshooting, et la personnalisation.
