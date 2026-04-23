#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════
║          PIPELINE YOUTUBE MUSIC — CHAÎNE MUSIQUE IA             ║
║          Génère et publie automatiquement 1 morceau/jour        ║
════════════════════════════════════════════════════════════════════
Étapes :
  1. Génère un concept de chanson (Google Gemini) — ou utilise le prompt manuel
  2. Génère la musique (Replicate MusicGen)
  3. Génère la pochette d'album (Pillow)
  4. Assemble la vidéo MP4  (FFmpeg : image fixe + audio)
  5. Génère la miniature YouTube (Pillow)
  6. Uploade sur YouTube (YouTube Data API v3)
Usage :
  python daily_music.py                         # run complet automatique
  python daily_music.py --dry-run               # pas d'upload, pas de commit
  python daily_music.py --publish-now           # publie immédiatement (pas à 18h)

Variables d'environnement spéciales (injectées par le workflow manuel) :
  MANUAL_PROMPT   — remplace Gemini si défini
  PUBLISH_NOW     — "true" pour publier immédiatement
"""
import os
import sys
import json
import math
import time
import random
import logging
import argparse
import textwrap
import subprocess
import tempfile
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from google import genai
from google.oauth2.credentials import Credentials
import google.auth.exceptions
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ═════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════
CHANNEL_NAME       = "Pop Électro Lab"
ARTIST_NAME        = "Adrianna"
VIDEO_WIDTH        = 1920
VIDEO_HEIGHT       = 1080
VIDEO_FPS          = 30
GEMINI_MODEL       = "gemini-2.5-flash"

BG_DARK_1    = (10, 5, 20)
BG_DARK_2    = (25, 10, 50)
ACCENT_RGB   = (138, 43, 226)
ACCENT_2_RGB = (0, 206, 209)
TEXT_WHITE    = (255, 255, 255)
TEXT_GREY     = (180, 180, 200)

PUBLISH_HOUR_PARIS = 18
UTC_OFFSET         = 2

SONGS_FILE     = Path(__file__).parent / "songs_done.json"
CAMPAIGNS_FILE = Path(__file__).parent / "campaigns.json"

ALL_THEMES = [
    # ── DAVID GUETTA x FEMALE POWER ──────────────────────────────────
    "upbeat electronic dance pop with soaring warm synth chords and powerful female soprano belting an emotional chorus with vibrato. Driving rhythm, euphoric energy, radio-ready hit.",
    "electronic pop dance with a bold punchy beat, bright catchy synth lead, and a charismatic female voice delivering a massive sing-along chorus. Commercial summer dancefloor energy.",
    "emotional electronic dance ballad with piano intro dissolving into lush synth pads and a soaring female voice full of passion and harmonies. Euphoric chorus, bittersweet feeling.",
    "high-energy pop electronic track with bright plucked synth melody, driving beat, and a powerful soprano building to an explosive emotional chorus. Uplifting and warm.",
    "dark yet euphoric electronic pop with deep warm bass, cinematic build-up tension, then a soaring female vocal cutting through into a catchy chorus. Sophisticated club feel.",
    "feel-good dance pop with groovy electronic production, bouncy beat, catchy synth hook, and a smooth confident female voice. Fun, infectious, summer hit energy.",
    "powerful stadium-scale electronic pop with sweeping strings, orchestral synths, dramatic build-up, and a massive belting chorus from a soprano with huge range.",
    "intimate electronic pop that starts soft and warm with just keys and voice, then blossoms into a bold uplifting chorus with synths and emotional female belting.",
    "electronic dance pop with a nostalgic melancholy edge — warm retro synths, dreamy chord progression, and a bittersweet female vocal performance. Beautiful and euphoric.",
    "catchy upbeat electronic pop with tropical warm synth textures, bright playful melody, and a joyful female voice full of positive energy. Summer anthem, radio-ready.",

    # ── ARIANA GRANDE WHISTLE REGISTER / EMOTIONAL ───────────────────
    "emotional pop with electronic production — breathy intimate female voice rising to powerful whistle-register notes over warm synth chords and gentle driving beat. Vulnerable and stunning.",
    "modern pop dance with a sleek electronic production, confident female voice with silky smooth tone, catchy hooky chorus, and lush harmonic layers. Polished and commercial.",
    "uplifting electronic pop ballad with a female voice that starts intimate and fragile, then explodes into a powerful belted chorus over soaring warm synths. Emotionally moving.",
    "danceable pop electronic track with a playful bouncy beat, bright layered female harmonies, catchy melodic hook, and a feel-good joyful energy. Summer bop.",
    "cinematic electronic pop with a female voice conveying raw emotion and strength. Dramatic build from quiet verses to a massive euphoric chorus with lush synth layers.",
    "smooth yet energetic electronic pop with warm bass groove, catchy synth arpeggios, and a soulful female voice blending pop and R&B inflections into a radio hit.",
    "bold empowerment electronic pop anthem with driving beat, bright aggressive synths, and a powerful female soprano delivering a passionate, defiant, uplifting chorus.",
    "soft dreamy electronic pop with ethereal synth pads, gentle warm production, and a light airy female voice with emotional depth. Builds gradually into a catchy euphoric drop.",
    "retro-influenced modern pop electronic with warm analog synths, funky bass, and a charismatic female voice with attitude. Nostalgic yet fresh, irresistibly catchy.",
    "emotional dance pop with vulnerable verses and an explosive uplifting chorus. Female voice conveys heartbreak turning into strength. Warm synths, driving beat, powerful harmonies.",

    # ── JAZZY — GROOVY SOUL ELECTRONIC ───────────────────────────────
    "electronic pop with a smooth jazz influence — warm chord progressions, subtle groove, bright synth melody, and a silky female voice blending soul and pop. Sophisticated and catchy.",
    "groovy dance electronic with funky bass line, warm synth chords, and a smooth charismatic female voice. Upbeat summer groove, feel-good energy, memorable chorus.",
    "upbeat pop electronic with a jazzy harmonic richness — lush chords, warm keys, bright synth accents, and a confident expressive female voice. Sophisticated commercial pop.",
    "feel-good electronic pop with a soulful warmth — soft synth pads, gentle groove, and a female voice with natural emotion and richness. Smooth, catchy, radio-ready.",
    "modern electronic pop with jazz-influenced chord voicings, warm atmospheric synths, and a female vocalist with a unique expressive tone. Elegant and emotionally resonant.",
    "dance pop with a sophisticated groove — syncopated beat, warm bass, bright melodic synths, and a female voice with soulful delivery and powerful chorus moments.",
    "uplifting electronic pop ballad with jazz harmony DNA — rich warm chords, emotional progression, and a female voice with extraordinary control and passion. Beautiful and commercial.",
    "playful bouncy electronic pop with a jazzy fun energy — bright warm synths, catchy melodic hook, and a charismatic female voice full of joy and personality. Pure feel-good.",
    "electronic pop with orchestral warmth — strings, piano, lush synths, and a soprano female voice with incredible emotional range. Builds to a stunning uplifting chorus.",
    "smooth dance electronic with an R&B-influenced groove, warm deep synth bass, bright catchy melody, and a confident silky female voice. Urban pop crossover hit.",

    # ── COLLABORATIONS ÉCLECTIQUES ────────────────────────────────────
    "euphoric dance electronic pop with two contrasting vocal energies — a powerful soprano and a second smoother voice trading lines on a catchy call-and-response chorus.",
    "summer dance hit with warm tropical synths, upbeat driving energy, bright catchy hook, and a passionate female voice building from intimate verses to a massive chorus.",
    "emotional electronic pop with a cinematic atmosphere — sweeping synth strings, warm pads, and a female voice performing with theatrical drama and vulnerability. Moving and euphoric.",
    "modern commercial dance pop with a huge infectious chorus, bright layered synths, punchy beat, and a female voice designed to get stuck in your head for days.",
    "uplifting motivational electronic pop anthem — bright bold synths, driving powerful beat, and a soprano female voice with an inspiring, empowering emotional delivery.",
    "warm nostalgic electronic pop love song — retro synth textures, gentle groove, and a tender female voice singing with heartfelt emotion and beautiful melodic phrasing.",
    "bold energetic dance pop with an edgy electronic production, driving aggressive beat, and a fierce powerful female voice with attitude and incredible vocal presence.",
    "dreamy euphoric electronic pop with shimmering synth arpeggios, warm lush atmosphere, and a floating ethereal female voice that rises to emotional powerful moments.",
    "catchy radio-ready dance electronic pop with a bright irresistible hook, punchy beat, warm synth chords, and a female voice with charisma, power and perfect pitch.",
    "late-night emotional electronic pop — darker warm tones, intimate breathy female voice building to a vulnerable yet powerful chorus. Sophisticated, moving, and beautifully produced.",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════
# CAMPAGNES MUSICALES
# ════════════════════════════════════════════════════════════════════

def load_active_campaign() -> dict | None:
    if not CAMPAIGNS_FILE.exists():
        return None
    try:
        with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Impossible de lire campaigns.json : {e}")
        return None
    today = datetime.now(timezone.utc).date()
    for campaign in data.get("campaigns", []):
        try:
            start = datetime.strptime(campaign["start"], "%Y-%m-%d").date()
            end   = datetime.strptime(campaign["end"],   "%Y-%m-%d").date()
            if start <= today <= end:
                logger.info(f"Campagne active : « {campaign.get('description', '?')} »")
                return campaign
        except (KeyError, ValueError) as e:
            logger.warning(f"Campagne malformée ignorée : {e}")
    logger.info("Aucune campagne active — thème aléatoire.")
    return None

# ════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ════════════════════════════════════════════════════════════════════

def send_failure_notification(error_msg: str, step: str = "inconnu") -> None:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    sender    = os.environ.get("GMAIL_SENDER")
    password  = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("NOTIFICATION_EMAIL")
    if not all([sender, password, recipient]):
        logger.warning("Secrets email manquants — notification non envoyee.")
        return
    msg = MIMEMultipart()
    msg["Subject"] = f"YouTube Music Bot — Echec pipeline : {step}"
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(f"Etape : {step}\nErreur : {error_msg}", "plain"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(sender, password)
            server.send_message(msg)
    except Exception as e:
        logger.warning(f"Impossible d'envoyer la notification : {e}")

def load_songs_done() -> dict:
    if SONGS_FILE.exists():
        with open(SONGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "count": 0}

def save_songs_done(data: dict) -> None:
    with open(SONGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"songs_done.json mis à jour ({data['count']} morceaux publiés).")

def retry(fn, retries=3, delay=5, label=""):
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            logger.warning(f"{label} — tentative {attempt}/{retries} échouée : {e}")
            if attempt < retries:
                time.sleep(delay * attempt)
    raise RuntimeError(f"{label} — toutes les tentatives ont échoué.")

# ════════════════════════════════════════════════════════════════════
# ÉTAPE 1 — GÉNÉRATION DU CONCEPT (GEMINI)
# ════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
You are the artistic director of a premium commercial pop electronic YouTube channel.
Your mission: create original, ultra-catchy, radio-ready song concepts in the style of
David Guetta, Jazzy (UK jazz-pop), and Ariana Grande — but with original titles and no
direct references to real artists.

TARGET SOUND — ALWAYS MATCH THIS:
- Genre: commercial electronic pop, dance pop, electro-pop, pop dance
- Female vocals: powerful soprano with emotion and vibrato (Ariana-style range),
  OR smooth silky jazz-influenced voice (Jazzy-style), OR both combined
- Production: warm uplifting synths, emotional chord progressions, catchy memorable melodies,
  driving beats — polished, euphoric, chart-ready
- Mood: euphoric, uplifting, emotional, empowering, romantic, or bittersweet-beautiful
  — NEVER aggressive, dark, or melancholic without a euphoric resolution

MUSIC PROMPT RULES — CRITICAL (sent directly to ElevenLabs AI music generator):
- Write 2-3 SHORT sentences (max 55 words total)
- Describe FEELING, ENERGY, INSTRUMENTS, VOCAL STYLE — nothing else
- FORBIDDEN words (cause API rejection): "festival", "rave", "mainstage", "anthem",
  "BPM", "four-on-the-floor", "sidechain", "supersaw", "chirp", "EDM", "techno",
  any real artist names (David Guetta, Ariana, Jazzy, etc.)
- GOOD descriptors: upbeat, driving, soaring, warm, bright, euphoric, emotional,
  uplifting, catchy, groovy, smooth, powerful, intimate, lush, radiant, tender,
  synth, electronic, pop, dance, piano, strings, vocals, chorus, harmonies, vibrato

SONG TITLE: punchy, commercial, in English — max 4 words. Avoid clichés like "Neon" or "Fire".

Return ONLY valid JSON:
{
  "titre": "Song Title",
  "genre_tags": "dance pop, electronic pop, female vocals, euphoric, commercial pop",
  "music_prompt": "A warm upbeat electronic pop track with soaring synth chords and a driving rhythm. Features a powerful soprano female voice with vibrato building into an emotional, catchy chorus. Bright, uplifting energy designed to make people dance and feel alive.",
  "description_youtube": "SEO-optimized description with hashtags #ElectronicPop #DancePop #PopMusic #ElectronicMusic",
  "tags_youtube": ["electronic pop", "dance pop", "female vocals", "uplifting", "commercial pop"],
  "theme_slug": "short-slug",
  "mood": "euphoric",
  "color_accent": "#FF00FF"
}
"""

def generate_song_concept(
    songs_done: dict,
    dry_run: bool = False,
    manual_prompt: str | None = None,
) -> dict:
    logger.info("═══ ÉTAPE 1 : Génération du concept ═══")

    if dry_run:
        logger.info("[DRY-RUN] Génération simulée.")
        return {
            "titre": "[DRY-RUN] Neon Nights",
            "genre_tags": "electronic pop, synth wave, dance",
            "music_prompt": "An euphoric EDM festival anthem at 128 BPM in G minor. Features massive supersaw lead synths, punchy four-on-the-floor kick, and a powerful female soprano vocal belting an emotional hook.",
            "description_youtube": "[DRY-RUN] Test. #AIMusic",
            "tags_youtube": ["ai music", "electro pop", "synthwave"],
            "theme_slug": "dry-run-test",
            "mood": "euphoric",
            "color_accent": "#FF00FF",
        }

    if manual_prompt:
        logger.info(f"Prompt manuel : « {manual_prompt} »")
        full_prompt = f"""{SYSTEM_PROMPT}

The user has requested a specific musical style/theme for today's track.
Develop a complete song concept based on this exact request:

"{manual_prompt}"

Generate the complete concept (title, ENGLISH lyrics, tags, YouTube description).
Use the user's request as the theme_slug (slugified).
"""
    else:
        campaign = load_active_campaign()
        if campaign:
            theme_text = campaign["style_prompt"]
        else:
            done_slugs = set(songs_done.get("done", []))
            available = [t for t in ALL_THEMES if t not in done_slugs]
            if not available:
                available = ALL_THEMES.copy()
            candidates = random.sample(available, min(5, len(available)))
            theme_text = "\n".join(f"- {c}" for c in candidates)

        full_prompt = f"""{SYSTEM_PROMPT}

Here are possible themes for today's track. Pick the most inspiring one:

{theme_text}

Generate the complete song concept (title, ENGLISH lyrics, tags, YouTube description).
The chosen theme must appear in theme_slug as a short slug.
"""

    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    def call_gemini():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.85,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip().lstrip("\ufeff")
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Impossible de parser la réponse Gemini. Début: {raw[:200]}")

    result = retry(call_gemini, retries=3, delay=10, label="Gemini API")
    for key in ("titre", "genre_tags", "music_prompt", "description_youtube", "tags_youtube", "theme_slug", "mood"):
        if key not in result:
            raise ValueError(f"Clé manquante : {key}")
    logger.info(f"Concept : « {result['titre']} » — {result['genre_tags']}")
    return result

# ════════════════════════════════════════════════════════════════════
# ÉTAPE 2 — GÉNÉRATION MUSIQUE (ElevenLabs Music API)
# ════════════════════════════════════════════════════════════════════
# API officielle ElevenLabs Music (synchrone — retourne le MP3 directement).
# Secret requis : ELEVENLABS_API_KEY
# Endpoint : POST https://api.elevenlabs.io/v1/music
# Durée max : 5 minutes (300 000 ms)

ELEVENLABS_API_BASE        = "https://api.elevenlabs.io/v1"
ELEVENLABS_MUSIC_DURATION_MS = 150000  # 2 min 30 s


def generate_music(music_prompt: str, output_mp3, dry_run: bool = False) -> dict:
    """Génère le morceau via l'API ElevenLabs Music (synchrone, pas de polling).

    Retourne un dict avec au minimum {id, audio_url, duration}.
    """
    logger.info("═══ ÉTAPE 2 : Génération musique (ElevenLabs) ═══")

    if dry_run:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", "30", "-q:a", "2", "-acodec", "libmp3lame", str(output_mp3)],
            check=True, capture_output=True,
        )
        return {"id": "dry-run", "audio_url": str(output_mp3), "duration": 30.0}

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY manquant — ajouter dans les secrets GitHub."
        )

    def _call_elevenlabs(prompt: str):
        logger.info(f"POST {ELEVENLABS_API_BASE}/music — prompt: {prompt[:100]}…")
        return requests.post(
            f"{ELEVENLABS_API_BASE}/music",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
            params={"output_format": "mp3_44100_128"},
            json={
                "prompt": prompt,
                "music_length_ms": ELEVENLABS_MUSIC_DURATION_MS,
                "force_instrumental": False,
            },
            timeout=300,
        )

    # Prompts de secours garantis sans mots interdits par ElevenLabs
    _SAFE_FALLBACKS = [
        "An upbeat electronic pop track with soaring lead synths and a driving rhythm. "
        "Features powerful female vocals building into an emotional, catchy chorus. "
        "Bright and energetic dance music.",
        "Energetic electronic dance music with warm synth melodies and strong female vocals. "
        "Uplifting and catchy with a memorable chorus and driving beat.",
        "Euphoric electronic pop song with sweeping synths, emotional female vocals, "
        "and an uplifting chorus. Feel-good dance music with a bright, positive energy.",
    ]

    def _try_call(prompt: str) -> requests.Response:
        """Appelle ElevenLabs et retourne la réponse. Lève si bad_prompt définitif."""
        rsp = _call_elevenlabs(prompt)
        if rsp.status_code != 400:
            return rsp
        try:
            detail = rsp.json().get("detail", {})
            if not (isinstance(detail, dict) and detail.get("code") == "bad_prompt"):
                return rsp  # autre erreur 400 — remonter au niveau supérieur
        except ValueError:
            return rsp
        return None  # signal : bad_prompt détecté

    # Tentative 1 : prompt Gemini original
    r = _try_call(music_prompt)

    # Tentative 2 : prompt_suggestion fourni par ElevenLabs
    if r is None:
        try:
            suggestion = (
                requests.post(
                    f"{ELEVENLABS_API_BASE}/music",
                    headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                    params={"output_format": "mp3_44100_128"},
                    json={"prompt": music_prompt, "music_length_ms": ELEVENLABS_MUSIC_DURATION_MS,
                          "force_instrumental": False},
                    timeout=30,
                ).json().get("detail", {}).get("data", {}).get("prompt_suggestion", "")
            )
        except Exception:
            suggestion = ""

        if suggestion and len(suggestion) > 20:
            logger.warning(f"ElevenLabs bad_prompt — retry suggestion : {suggestion[:100]}…")
            r = _try_call(suggestion)

    # Tentatives 3, 4, 5 : fallbacks sûrs prédéfinis
    if r is None:
        for i, fallback in enumerate(_SAFE_FALLBACKS, start=3):
            logger.warning(f"ElevenLabs bad_prompt — fallback #{i} : {fallback[:80]}…")
            r = _try_call(fallback)
            if r is not None:
                break

    if r is None:
        raise RuntimeError("ElevenLabs bad_prompt sur tous les prompts — vérifier les quotas ou la clé API.")

    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs music {r.status_code} : {r.text[:400]}")

    with open(output_mp3, "wb") as f:
        f.write(r.content)

    # ── Durée via ffprobe ────────────────────────────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(output_mp3)],
        capture_output=True, text=True,
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        duration = ELEVENLABS_MUSIC_DURATION_MS / 1000

    logger.info(f"Morceau ElevenLabs OK : {duration:.1f}s — {output_mp3}")
    return {
        "id": "elevenlabs",
        "audio_url": str(output_mp3),
        "duration": duration,
        "model": "eleven_music_v1",
    }


# ════════════════════════════════════════════════════════════════════
# ÉTAPE 3 — POCHETTE
# ════════════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return ACCENT_RGB
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def generate_album_art(titre, mood, color_accent, output_path, size=(1920, 1080)):
    logger.info("═══ ÉTAPE 3 : Pochette ═══")
    W, H = size
    accent = _hex_to_rgb(color_accent) if color_accent else ACCENT_RGB
    img = Image.new("RGB", (W, H))
    for y in range(H):
        for x in range(W):
            ratio = (x / W * 0.4 + y / H * 0.6)
            r = int(BG_DARK_1[0] + ratio * (BG_DARK_2[0] - BG_DARK_1[0]))
            g = int(BG_DARK_1[1] + ratio * (BG_DARK_2[1] - BG_DARK_1[1]))
            b = int(BG_DARK_1[2] + ratio * (BG_DARK_2[2] - BG_DARK_1[2]))
            img.putpixel((x, y), (r, g, b))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    random.seed(hash(titre))
    for _ in range(8):
        cx, cy = random.randint(0, W), random.randint(0, H)
        radius = random.randint(100, 350)
        alpha = random.randint(15, 40)
        color = (min(255, accent[0]+random.randint(-30,30)), min(255, accent[1]+random.randint(-30,30)),
                 min(255, accent[2]+random.randint(-30,30)), alpha)
        ov_draw.ellipse([(cx-radius, cy-radius), (cx+radius, cy+radius)], fill=color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=60))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (W, 5)], fill=accent)
    draw.rectangle([(0, H-5), (W, H)], fill=accent)
    def load_font(size, bold=True):
        paths = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
                 if bold else
                 ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
        for fp in paths:
            if Path(fp).exists():
                try: return ImageFont.truetype(fp, size)
                except Exception: continue
        return ImageFont.load_default()
    title_font = load_font(72)
    lines = textwrap.wrap(titre, width=25)
    y_start = (H // 2) - (len(lines) * 90 // 2) - 30
    for line in lines[:3]:
        bbox = draw.textbbox((0,0), line, font=title_font)
        tw = bbox[2] - bbox[0]
        x_pos = (W - tw) // 2
        draw.text((x_pos+3, y_start+3), line, font=title_font, fill=(0,0,0))
        draw.text((x_pos, y_start), line, font=title_font, fill=TEXT_WHITE)
        y_start += 90
    badge_font = load_font(32)
    mood_text = f"◆  {mood.upper()}"
    badge_bbox = draw.textbbox((0,0), mood_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 40
    badge_x = (W - badge_w) // 2
    badge_y = y_start + 30
    draw.rounded_rectangle([(badge_x, badge_y), (badge_x+badge_w, badge_y+50)], radius=25, fill=accent)
    draw.text((badge_x+20, badge_y+8), mood_text, font=badge_font, fill=TEXT_WHITE)
    ch_font = load_font(34, bold=False)
    ch_text = f"▶ {CHANNEL_NAME}"
    ch_bbox = draw.textbbox((0,0), ch_text, font=ch_font)
    draw.text(((W - (ch_bbox[2]-ch_bbox[0])) // 2, H-70), ch_text, font=ch_font, fill=TEXT_GREY)
    bar_count = 60
    bar_w = W // (bar_count * 2)
    bar_base_y = H - 100
    random.seed(hash(titre) + 42)
    for i in range(bar_count):
        bar_h = random.randint(10, 80)
        bx = i * (bar_w + bar_w) + (W - bar_count * bar_w * 2) // 2
        ar = bar_h / 80
        bar_color = (int(accent[0]*ar+30*(1-ar)), int(accent[1]*ar+30*(1-ar)), int(accent[2]*ar+30*(1-ar)))
        draw.rectangle([(bx, bar_base_y-bar_h), (bx+bar_w, bar_base_y)], fill=bar_color)
    img.save(output_path, "PNG", quality=95)
    logger.info(f"Pochette : {output_path}")

# ════════════════════════════════════════════════════════════════════
# ÉTAPE 3b — POCHETTE STREAMING 3000×3000 (DistroKid / Spotify / Apple)
# ════════════════════════════════════════════════════════════════════

def generate_square_art(titre: str, mood: str, color_accent: str, output_path, size: int = 3000) -> None:
    """Génère une pochette carrée 3000×3000 qualité streaming professionnelle.

    Design : fond sombre multicouche (halos, bokeh, cercles concentriques),
    titre grand format, nom d'artiste Adrianna, badge mood, label AI GENERATED MUSIC.
    """
    logger.info("═══ ÉTAPE 3b : Pochette streaming 3000×3000 (Adrianna) ═══")
    S = size
    accent = _hex_to_rgb(color_accent) if color_accent else ACCENT_RGB

    def load_font(px, bold=True):
        paths = (
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
            if bold else
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
        )
        for fp in paths:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, px)
                except Exception:
                    continue
        return ImageFont.load_default()

    # ── Fond de base : très sombre, teinté par la couleur accent ─────
    base = (
        max(4,  min(20, accent[0] // 10)),
        max(3,  min(14, accent[1] // 11)),
        max(10, min(30, accent[2] //  9)),
    )
    canvas = Image.new("RGBA", (S, S), (*base, 255))

    # ── Halo principal (grand blur unique = look lumineux haut de gamme) ──
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    m    = S // 5
    gd.ellipse([(m, m), (S - m, S - m)],                       fill=(*accent, 50))
    gd.ellipse([(S * 3 // 8, S * 3 // 8), (S * 5 // 8, S * 5 // 8)], fill=(*accent, 35))
    comp = (min(255, accent[2] + 40), min(255, accent[0] // 2 + 20), min(255, accent[0] + 60))
    gd.ellipse([(-S // 4, -S // 4), (S // 2, S // 2)], fill=(*comp, 18))
    gd.ellipse([(S // 2, S // 2), (S + S // 4, S + S // 4)], fill=(*comp, 14))
    glow   = glow.filter(ImageFilter.GaussianBlur(radius=S // 10))
    canvas = Image.alpha_composite(canvas, glow)

    # ── Bokeh : points de lumière flous colorés (un seul blur) ───────
    bokeh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd    = ImageDraw.Draw(bokeh)
    random.seed(hash(titre))
    palette = [
        (*accent, 70),
        (min(255, accent[0] + 100), min(255, accent[1] + 30), 255, 55),
        (255, min(255, accent[1] + 60), min(255, accent[2] + 80), 45),
        (210, 210, 255, 60),
    ]
    for _ in range(18):
        cx = random.randint(S // 8, S * 7 // 8)
        cy = random.randint(S // 8, S * 7 // 8)
        r  = random.randint(S // 42, S // 13)
        bd.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=random.choice(palette))
    bokeh  = bokeh.filter(ImageFilter.GaussianBlur(radius=S // 22))
    canvas = Image.alpha_composite(canvas, bokeh)

    # ── Cercles concentriques décoratifs (sans blur — rapide) ─────────
    rd = ImageDraw.Draw(canvas)
    for r_size in range(S // 5, S * 7 // 10, S // 8):
        alpha = max(5, 25 - int(r_size * 22 / S))
        rd.ellipse(
            [(S // 2 - r_size, S // 2 - r_size), (S // 2 + r_size, S // 2 + r_size)],
            outline=(*accent, alpha), width=4,
        )

    canvas = canvas.convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    # ══ TYPOGRAPHIE ═══════════════════════════════════════════════════

    # ── Titre (grand, centré, décalé légèrement vers le haut) ────────
    title_font = load_font(int(S * 0.054), bold=True)
    lines = textwrap.wrap(titre.upper(), width=17)[:3]
    lh    = int(S * 0.068)
    y     = S // 2 - (len(lines) * lh) // 2 - int(S * 0.08)

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        tw   = bbox[2] - bbox[0]
        x    = (S - tw) // 2
        draw.text((x + 9, y + 9), line, font=title_font, fill=(0, 0, 0))
        draw.text((x + 3, y + 3), line, font=title_font,
                  fill=(accent[0] // 4, accent[1] // 4, accent[2] // 4))
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += lh

    # ── Séparateur avec diamant central ───────────────────────────────
    sep_y  = y + int(S * 0.024)
    half_w = int(S * 0.12)
    cx_s   = S // 2
    dm     = 13
    draw.rectangle([(cx_s - half_w, sep_y), (cx_s - int(S * 0.016), sep_y + 4)], fill=accent)
    draw.polygon([
        (cx_s, sep_y - dm), (cx_s + dm, sep_y + 2),
        (cx_s, sep_y + dm + 4), (cx_s - dm, sep_y + 2),
    ], fill=accent)
    draw.rectangle([(cx_s + int(S * 0.016), sep_y), (cx_s + half_w, sep_y + 4)], fill=accent)

    # ── Nom d'artiste ADRIANNA ────────────────────────────────────────
    artist_font = load_font(int(S * 0.040), bold=False)
    a_text      = ARTIST_NAME.upper()
    bbox        = draw.textbbox((0, 0), a_text, font=artist_font)
    ax          = (S - (bbox[2] - bbox[0])) // 2
    ay          = sep_y + int(S * 0.032)
    draw.text((ax + 5, ay + 5), a_text, font=artist_font, fill=(0, 0, 0))
    draw.text((ax, ay), a_text, font=artist_font,
              fill=(min(255, accent[0] + 90), min(255, accent[1] + 70), min(255, accent[2] + 90)))

    # ── Badge mood (pill arrondie) ─────────────────────────────────────
    badge_font = load_font(int(S * 0.019))
    b_text     = f"◆  {mood.upper()}  ◆"
    bbox       = draw.textbbox((0, 0), b_text, font=badge_font)
    pad_x, pad_y = int(S * 0.022), int(S * 0.012)
    bw  = bbox[2] - bbox[0] + pad_x * 2
    bh  = bbox[3] - bbox[1] + pad_y * 2
    bx  = (S - bw) // 2
    by  = S - int(S * 0.16)
    draw.rounded_rectangle(
        [(bx, by), (bx + bw, by + bh)],
        radius=bh // 2, fill=accent,
        outline=(255, 255, 255), width=2,
    )
    draw.text(
        ((S - (bbox[2] - bbox[0])) // 2, by + pad_y),
        b_text, font=badge_font, fill=(255, 255, 255),
    )

    # ── Label DistroKid obligatoire : AI GENERATED MUSIC ─────────────
    ai_font = load_font(int(S * 0.015), bold=False)
    ai_text = "✦  AI GENERATED MUSIC  ✦"
    bbox    = draw.textbbox((0, 0), ai_text, font=ai_font)
    draw.text(
        ((S - (bbox[2] - bbox[0])) // 2, S - int(S * 0.072)),
        ai_text, font=ai_font, fill=(155, 155, 175),
    )

    # ── Cadre décoratif accent (4 bordures) ───────────────────────────
    b = int(S * 0.007)
    draw.rectangle([(b, b), (S - b, b + 6)],          fill=accent)
    draw.rectangle([(b, S - b - 6), (S - b, S - b)],  fill=accent)
    draw.rectangle([(b, b), (b + 6, S - b)],           fill=accent)
    draw.rectangle([(S - b - 6, b), (S - b, S - b)],  fill=accent)

    canvas.save(str(output_path), "JPEG", quality=97, optimize=True)
    logger.info(f"Pochette streaming 3000×3000 : {output_path}")


# ════════════════════════════════════════════════════════════════════
# ÉTAPE 4 — VIDÉO
# ════════════════════════════════════════════════════════════════════

def generate_video(audio_path, album_art_path, output_mp4, dry_run=False):
    logger.info("═══ ÉTAPE 4 : Vidéo FFmpeg ═══")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(audio_path)], capture_output=True, text=True, check=True)
    logger.info(f"Durée audio : {probe.stdout.strip()}s")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(album_art_path), "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "256k",
           "-r", str(VIDEO_FPS), "-shortest", "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(output_mp4)]
    if dry_run:
        cmd.insert(-1, "-t"); cmd.insert(-1, "5")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error(result.stderr[-3000:])
        raise RuntimeError(f"FFmpeg échoué (code {result.returncode})")
    logger.info(f"Vidéo : {output_mp4}")

# ════════════════════════════════════════════════════════════════════
# ÉTAPE 5 — MINIATURE
# ════════════════════════════════════════════════════════════════════

def _pexels_search_query(genre_tags: str) -> str:
    """Déduit la requête Pexels optimale depuis les genre_tags Gemini/MusicGen."""
    tags = genre_tags.lower()
    if any(k in tags for k in ("lo-fi", "lofi", "jazz", "piano", "rainy", "cozy")):
        return "woman cozy jazz cafe aesthetic rainy"
    if any(k in tags for k in ("afrobeats", "amapiano", "afro", "tropical")):
        return "woman dancing african vibrant tropical"
    if any(k in tags for k in ("synthwave", "cyberpunk", "neon", "retro 80")):
        return "woman neon retro synthwave city night"
    if any(k in tags for k in ("hip hop", "rap", "urban", "trap")):
        return "woman urban street style hip hop"
    if any(k in tags for k in ("classical", "orchestral", "piano", "cinematic")):
        return "woman elegant classical music concert"
    if any(k in tags for k in ("ambient", "meditation", "nature", "ethereal")):
        return "woman nature dreamy fog serene"
    if any(k in tags for k in ("electro", "techno", "rave", "festival", "dance")):
        return "woman dancing festival rave electronic music"
    if any(k in tags for k in ("pop", "indie pop", "electro pop")):
        return "woman music aesthetic pop colorful"
    if any(k in tags for k in ("house", "deep house", "club")):
        return "woman night club dance lights"
    # Fallback générique
    return "woman music aesthetic studio"


def generate_thumbnail(titre, mood, color_accent, genre_tags, output_path):
    logger.info("═══ ÉTAPE 5 : Miniature (Pexels) ═══")
    W, H = 1280, 720
    accent = _hex_to_rgb(color_accent) if color_accent else ACCENT_RGB

    def load_font(size, bold=True):
        paths = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
                 if bold else
                 ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"])
        for fp in paths:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    # ── Récupération photo Pexels ──────────────────────────────────────
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    img = None

    if pexels_key:
        query = _pexels_search_query(genre_tags)
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": pexels_key},
                params={"query": query, "orientation": "landscape", "size": "large", "per_page": 10},
                timeout=15,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if photos:
                # Sélection aléatoire parmi les 10 premiers pour varier
                photo = random.choice(photos)
                photo_url = photo["src"]["large2x"]
                dl = requests.get(photo_url, timeout=30)
                dl.raise_for_status()
                img = Image.open(BytesIO(dl.content)).resize((W, H), Image.LANCZOS)
                logger.info(f"Photo Pexels : {photo['url']} — requête : «{query}»")
            else:
                logger.warning(f"Pexels : aucune photo pour «{query}», fallback Pillow.")
        except Exception as e:
            logger.warning(f"Pexels KO ({e}), fallback Pillow.")
    else:
        logger.warning("PEXELS_API_KEY absent — fallback Pillow.")

    # ── Fallback : fond dégradé Pillow (si Pexels indisponible) ───────
    if img is None:
        img = Image.new("RGB", (W, H))
        draw_bg = ImageDraw.Draw(img)
        for y in range(H):
            ratio = y / H
            draw_bg.line(
                [(0, y), (W, y)],
                fill=(
                    int(BG_DARK_1[0] + ratio * (BG_DARK_2[0] - BG_DARK_1[0])),
                    int(BG_DARK_1[1] + ratio * (BG_DARK_2[1] - BG_DARK_1[1])),
                    int(BG_DARK_1[2] + ratio * (BG_DARK_2[2] - BG_DARK_1[2])),
                ),
            )

    # ── Overlay sombre en bas pour lisibilité du texte ─────────────────
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    # Gradient vertical : transparent en haut → 70% opaque en bas
    for y in range(H // 3, H):
        alpha = int(200 * (y - H // 3) / (H - H // 3))
        ov_draw.rectangle([(0, y), (W, y + 1)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # ── Badge "AI MUSIC LAB" en haut à gauche ─────────────────────────
    badge_font = load_font(28)
    badge_text = "◆ AI MUSIC LAB"
    draw.rounded_rectangle([(30, 30), (280, 75)], radius=10, fill=(*accent, 220))
    draw.text((50, 40), badge_text, font=badge_font, fill=TEXT_WHITE)

    # ── Titre centré en bas ────────────────────────────────────────────
    title_font = load_font(62)
    lines = textwrap.wrap(titre, width=24)[:3]
    total_h = len(lines) * 76
    y_title = H - total_h - 90
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        tw = bbox[2] - bbox[0]
        x_pos = max(30, (W - tw) // 2)
        draw.text((x_pos + 2, y_title + 2), line, font=title_font,
                  fill=(0, 0, 0), stroke_width=1, stroke_fill=(0, 0, 0))
        draw.text((x_pos, y_title), line, font=title_font, fill=TEXT_WHITE)
        y_title += 76

    # ── Mood + genre en bas ────────────────────────────────────────────
    mood_font = load_font(34)
    mood_text = f"✦ {mood.upper()} ✦"
    bbox = draw.textbbox((0, 0), mood_text, font=mood_font)
    mw = bbox[2] - bbox[0]
    draw.text(((W - mw) // 2, H - 60), mood_text, font=mood_font,
              fill=tuple(min(255, c + 60) for c in accent))

    img.save(output_path, "JPEG", quality=95)
    logger.info(f"Miniature sauvegardée : {output_path}")

# ════════════════════════════════════════════════════════════════════
# ÉTAPE 6 — UPLOAD YOUTUBE
# ════════════════════════════════════════════════════════════════════

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_youtube_credentials():
    for k in ["YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"]:
        if not os.environ.get(k):
            raise RuntimeError(f"Secret manquant : {k}")
    creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YOUTUBE_CLIENT_ID"],
                        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], scopes=YOUTUBE_SCOPES)
    creds.refresh(Request())
    return creds

def _compute_publish_time(publish_now=False):
    now_utc = datetime.now(timezone.utc)
    if publish_now:
        publish_utc = now_utc + timedelta(minutes=3)
        logger.info(f"Publication immédiate → {publish_utc.strftime('%H:%M UTC')}")
    else:
        publish_utc = now_utc.replace(hour=PUBLISH_HOUR_PARIS - UTC_OFFSET, minute=0, second=0, microsecond=0)
        if publish_utc <= now_utc:
            publish_utc = now_utc + timedelta(minutes=5)
    return publish_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def upload_to_youtube(video_path, thumbnail_path, titre, description, tags, dry_run=False, publish_now=False):
    logger.info("═══ ÉTAPE 6 : Upload YouTube ═══")
    if dry_run:
        return "https://youtube.com/watch?v=DRY_RUN_ID"
    creds   = get_youtube_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    publish_at = _compute_publish_time(publish_now=publish_now)
    body = {
        "snippet": {"title": titre, "description": description, "tags": tags,
                    "categoryId": "10", "defaultLanguage": "en"},
        "status":  {"privacyStatus": "private", "publishAt": publish_at,
                    "selfDeclaredMadeForKids": False, "madeForKids": False},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=50*1024*1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info(f"  Upload : {int(status.progress()*100)}%")
        except HttpError as e:
            if e.resp.status in (500,502,503,504):
                time.sleep(10)
            else:
                raise
    video_id = response["id"]
    logger.info(f"Vidéo uploadée : {video_id}")
    try:
        youtube.thumbnails().set(videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")).execute()
    except HttpError as e:
        logger.warning(f"Miniature : {e}")
    return f"https://youtube.com/watch?v={video_id}"

# ════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish-now", action="store_true")
    args = parser.parse_args()

    manual_prompt = os.environ.get("MANUAL_PROMPT", "").strip() or None
    publish_now   = args.publish_now or os.environ.get("PUBLISH_NOW", "").lower() == "true"

    if args.dry_run:   logger.info("MODE DRY-RUN")
    if manual_prompt:  logger.info(f"PROMPT MANUEL : « {manual_prompt} »")
    if publish_now:    logger.info("PUBLICATION IMMÉDIATE")

    start_time = time.time()
    tmp_dir = Path(tempfile.mkdtemp(prefix="yt_music_"))

    try:
        audio_path      = tmp_dir / "song.mp3"
        album_art_path  = tmp_dir / "album_art.png"
        square_art_path = tmp_dir / "cover_3000x3000.jpg"
        video_path      = tmp_dir / "video.mp4"
        thumbnail_path  = tmp_dir / "thumbnail.jpg"

        songs_done = load_songs_done()
        concept    = generate_song_concept(songs_done, dry_run=args.dry_run, manual_prompt=manual_prompt)
        clip_data  = generate_music(concept["music_prompt"], audio_path, dry_run=args.dry_run)
        generate_album_art(concept["titre"], concept.get("mood","electronic"),
                           concept.get("color_accent","#8A2BE2"), album_art_path)
        generate_square_art(concept["titre"], concept.get("mood","electronic"),
                            concept.get("color_accent","#8A2BE2"), square_art_path)
        generate_video(audio_path, album_art_path, video_path, dry_run=args.dry_run)
        generate_thumbnail(concept["titre"], concept.get("mood","electronic"),
                           concept.get("color_accent","#8A2BE2"),
                           concept.get("genre_tags","electronic"), thumbnail_path)
        video_url = upload_to_youtube(video_path, thumbnail_path, concept["titre"],
                                      concept["description_youtube"], concept["tags_youtube"],
                                      dry_run=args.dry_run, publish_now=publish_now)

        # ── Copie des fichiers distro dans le workspace (artifact GitHub) ──
        if not args.dry_run:
            distro_dir  = Path(__file__).parent / "distro"
            distro_dir.mkdir(exist_ok=True)
            date_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            slug        = concept.get("theme_slug", "track")
            safe_slug   = slug[:40].replace("/", "-")
            base_name   = f"{date_str}_{safe_slug}"
            shutil.copy(audio_path,      distro_dir / f"{base_name}.mp3")
            shutil.copy(square_art_path, distro_dir / f"{base_name}_cover.jpg")
            logger.info(f"Fichiers distro → distro/{base_name}.*")

            songs_done["done"].append(concept["theme_slug"])
            songs_done["count"] = songs_done.get("count", 0) + 1
            songs_done["last_song"] = {
                "titre": concept["titre"], "url": video_url, "genre": concept["genre_tags"],
                "published": datetime.now(timezone.utc).isoformat(),
                "manual": bool(manual_prompt), "publish_now": publish_now,
                "distro_files": [f"{base_name}.mp3", f"{base_name}_cover.jpg"],
            }
            save_songs_done(songs_done)

        logger.info("=" * 60)
        logger.info(f"Pipeline terminé en {time.time()-start_time:.0f}s")
        logger.info(f"   Morceau : {concept['titre']}")
        logger.info(f"   URL     : {video_url}")
        logger.info("=" * 60)

    except Exception as e:
        error_str = str(e)
        step = ("Token YouTube" if "RefreshError" in error_str else
                "Quota API" if "quota" in error_str.lower() else
                "ElevenLabs" if "elevenlabs" in error_str.lower() else
                "Gemini" if "gemini" in error_str.lower() else
                "FFmpeg" if "ffmpeg" in error_str.lower() else "Pipeline")
        logger.exception(f"Echec ({step}) : {e}")
        send_failure_notification(error_str, step=step)
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
