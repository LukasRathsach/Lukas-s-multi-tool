<!-- AI-CONFIG:START -->
> Shared AI context: read `~/.claude/AI_CONFIG_INDEX.md` first, then this project file. Universal rules and skills live in `~/.claude/`; project-specific context stays here.
<!-- AI-CONFIG:END -->

# Video Tools — AGENTS.md

Dette er en Flask-baseret webapplikation der kører lokalt på Mac og tilbyder to værktøjer:
1. **Instagram Reel & YouTube Shorts downloader** — downloader videoer via yt-dlp
2. **MP4 → H.264 konverter** — konverterer videofiler til H.264 enkeltvis eller som mappe med ZIP-download

---

## Projektstruktur

```
insta reel bot/
├── app.py               # Hele applikationen (Flask backend + HTML/CSS/JS)
├── requirements.txt     # Python-afhængigheder
├── Dockerfile           # Til Railway-deployment (installerer ffmpeg via apt)
├── Procfile             # Gunicorn-kommando til Railway
├── nixpacks.toml        # Alternativ Railway-konfiguration (bruges ikke, Dockerfile har forrang)
├── .gitignore
├── AGENTS.md            # Denne fil
└── .Codex/
    └── launch.json      # Fortæller Codex hvordan serveren startes
```

---

## Sådan kører du lokalt

### Forudsætninger
- Python 3.11+
- ffmpeg (installér via `brew install ffmpeg`)
- yt-dlp, flask, flask-cors (installeres via pip)

### Start serveren
```bash
pip3 install flask flask-cors yt-dlp gunicorn
python3 app.py
```

Eller via Codex — Codex starter automatisk med `.Codex/launch.json` på port **5555**.

Åbn `http://localhost:5555` i browseren.

---

## Deployment til Railway

Projektet er deployed på Railway under service **"Insta-reel downloader"**.

### Deploy ny version
```bash
railway link          # Kun første gang, vælg projektet
railway up --service "Insta-reel downloader"
```

### Miljøvariabler på Railway
| Variabel | Beskrivelse |
|---|---|
| `INSTAGRAM_COOKIES` | Netscape-format cookies fra instagram.com (påkrævet for at undgå login-blokering) |
| `PORT` | Sættes automatisk af Railway |

### Hent din Railway-URL
```bash
railway domain --service "Insta-reel downloader"
```

### Cookies opdatering
Instagram cookies udløber hvis du logger ud. Når det sker:
1. Installer Chrome-extensionen **"Get cookies.txt LOCALLY"**
2. Gå til instagram.com (mens du er logget ind)
3. Eksportér cookies til en `.txt`-fil
4. Gå til Railway dashboard → service → Variables → opdatér `INSTAGRAM_COOKIES` med filens indhold
5. Railway genstarter automatisk

---

## Applikationens arkitektur

Al kode ligger i én fil: `app.py`. HTML, CSS og JavaScript er inline som Python-strings.

### Globale variabler ved opstart
```python
DOWNLOAD_DIR   # Temp-mappe til downloadede reels (ryddes ved ny download)
CONVERT_DIR    # Temp-mappe til konverterede filer og ZIP-filer
COOKIES_FILE   # Sti til temp-fil med Instagram-cookies (None hvis ikke sat)
```

### HTML-strenge
| Variabel | Beskrivelse |
|---|---|
| `COMMON_CSS` | Delt CSS for alle sider (mørkt tema, kort-layout, knapper) |
| `HOME_HTML` | Forsiden — vælg mellem de to værktøjer |
| `DOWNLOADER_HTML` | Downloader-siden |
| `CONVERTER_HTML` | Konverter-siden med Files/Folder-tabs |

---

## Routes

### GET `/`
Forsiden. Viser to kort: Downloader og Konverter.

### GET `/downloader`
Downloader-siden. Bruger kan paste en Instagram Reel eller YouTube Shorts URL.

### GET `/converter`
Konverter-siden med to tabs:
- **Files** — upload enkeltfiler, konvertér, download enkeltvis eller alle
- **Folder** — upload hel mappe, konvertér alle, download som ZIP med bevaret mappestruktur

### POST `/download`
**Body:** `{ "url": "https://www.instagram.com/reels/..." }`

Downloader video med yt-dlp. Returnerer `{ "stream_url": "/video/reel.mp4" }`.

Understøtter:
- `instagram.com` — Reels
- `youtube.com/shorts` — YouTube Shorts
- `youtube.com/watch` — Almindelige YouTube-videoer
- `youtu.be` — Korte YouTube-links

Format-prioritering: `bestvideo+bestaudio/best[acodec!=none]/best` med sortering på `hasaud,res,fps` — sikrer at video altid har lyd.

ffmpeg bruges til at merge separate video- og lydspor. Cookies bruges hvis `INSTAGRAM_COOKIES` er sat.

### GET `/video/<filename>`
Streamer en downloadet videofil til browseren. Filnavnet saniteres (kun `[\w.\-]` tilladt).

### POST `/convert`
**Form data:** `file` (videofil), `path` (relativ sti, bruges til ZIP)

Konverterer én fil til H.264 med ffmpeg:
```
ffmpeg -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k -movflags +faststart
```

Returnerer `{ "url": "/converted/<filename>" }`.

**iOS-kompatibilitet:** H.264 + AAC + faststart er den kombination der virker på alle Apple-enheder.

### GET `/converted/<filename>`
Serverer en konverteret fil som download.

### POST `/zip`
**Body:** `{ "files": [{ "serverUrl": "/converted/...", "relativePath": "folder/sub/file.mp4" }] }`

Samler konverterede filer i en ZIP og bevarer den originale mappestruktur. Returnerer `{ "url": "/download-zip/<filename>" }`.

### GET `/download-zip/<filename>`
Serverer ZIP-filen som download.

---

## Vigtige tekniske detaljer

### Hvorfor ffmpeg er kritisk
Instagram og YouTube leverer video og lyd som separate DASH-streams. yt-dlp downloader begge og bruger ffmpeg til at merge dem. Uden ffmpeg får man videofiler uden lyd.

På Railway installeres ffmpeg via `Dockerfile`:
```dockerfile
RUN apt-get update && apt-get install -y ffmpeg
```

Lokalt på Mac installeres det via Homebrew:
```bash
brew install ffmpeg
```

### Cache-busting
Alle video-URLs og konverter-URLs får et `?t=<timestamp>` suffix i frontend-koden, så browseren ikke cacher gamle filer når man downloader en ny video med samme filnavn.

### Gunicorn timeout
Procfile bruger `--timeout 600` og `--workers 2` for at håndtere store filer og lange konverteringer uden at serveren dræber forbindelsen.

### Fil-rydning
`DOWNLOAD_DIR` ryddes ved hver ny download-request for at spare diskplads. `CONVERT_DIR` ryddes ikke automatisk — konverterede filer og ZIP-filer lever, indtil serveren genstarter.

### Cookie-format
`INSTAGRAM_COOKIES` skal være i Netscape HTTP Cookie File-format:
```
# Netscape HTTP Cookie File
.instagram.com	TRUE	/	TRUE	<expiry>	<name>	<value>
```

Koden stripper automatisk eventuelle `<` og `>` der kan snige sig ind fra shell-escapering.

---

## Kendte begrænsninger

- **Private Instagram-videoer** kan ikke downloades — kræver at kontoen er offentlig
- **Cookies udløber** — typisk efter 30-90 dage eller ved logout
- **Store filer** tager tid — en 500 MB video kan tage flere minutter at konvertere
- **Mappeupload** bruger `webkitdirectory` — virker i Chrome og Edge, ikke i Safari
- **Én bruger ad gangen** på `/download` — DOWNLOAD_DIR deles og ryddes ved hver request, så samtidige downloads overskriver hinanden. Konvertering (`/convert`) er sikker da der bruges unikke temp-filer

---

## Lokal vs. Railway

| | Lokalt | Railway |
|---|---|---|
| Start | `python3 app.py` eller Codex | Automatisk |
| URL | `http://localhost:5555` | Fast Railway-URL |
| Tilgængeligt for andre | Nej (brug cloudflared) | Ja |
| ffmpeg | Skal installeres via brew | Installeres via Dockerfile |
| Cookies | Ikke nødvendigt (din Mac er logget ind) | Påkrævet via miljøvariabel |
| Pris | Gratis | Gratis tier |

---

## Hurtig fejlfinding

**"This video is private or requires login"**
→ Instagram cookies er ikke sat eller er udløbet. Opdatér `INSTAGRAM_COOKIES`.

**Video uden lyd**
→ ffmpeg er ikke installeret eller ikke fundet af yt-dlp. Kør `which ffmpeg` for at tjekke.

**500-fejl ved konvertering**
→ Se Railway-logs: `railway logs --service "Insta-reel downloader"`. Kig efter `[CONVERT ERROR]`.

**Siden viser gammel video**
→ Hård-refresh med Cmd+Shift+R.

**"Service Unavailable" i stedet for JSON**
→ Gunicorn timeout. Øg `--timeout` i Procfile og redeploy.
