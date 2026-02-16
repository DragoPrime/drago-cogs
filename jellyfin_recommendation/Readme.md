# Jellyfin Recommendation

Un cog pentru Red-DiscordBot care oferă recomandări săptămânale automate de anime și conținut adult de pe serverele Jellyfin.

## Caracteristici

- 🎬 Recomandări automate în fiecare luni la ora 18:00
- 🎌 Suport pentru anime cu integrare TMDb pentru postere și descrieri de calitate
- 🔞 Suport pentru conținut adult folosind metadata Jellyfin
- 🌐 Traducere automată a descrierilor în limba română
- ⚙️ Configurare separată pentru fiecare tip de conținut
- 🎲 Comenzi manuale pentru recomandări on-demand
- 📊 Afișare informații: gen, rating, link către server

## Cerințe

- Red-DiscordBot 3.5.0 sau mai nou
- Python 3.8+
- Dependențe Python:
  - `aiohttp`
  - `deep-translator`

## Instalare

### 1. Adaugă repository-ul (dacă este cazul)
```
[p]repo add jellyfin-rec <url-repository>
```

### 2. Instalează cog-ul
```
[p]cog install jellyfin-rec JellyfinRecommendation
```

### 3. Încarcă cog-ul
```
[p]load JellyfinRecommendation
```

### 4. Instalează dependențele
```
[p]pipinstall aiohttp deep-translator
```

## Configurare

### Configurare Anime
```
[p]animerecseturl <URL>
```
Setează URL-ul serverului Jellyfin pentru anime (ex: `https://jellyfin.example.com`)
```
[p]animerecsetapi <API_KEY>
```
Setează cheia API Jellyfin pentru anime
```
[p]animerecsettmdbapi <API_KEY>
```
Setează cheia API TMDb pentru anime (opțional dar recomandat)
```
[p]setanimerecommendationchannel <#canal>
```
Setează canalul unde vor fi trimise recomandările automate de anime
```
[p]setanimeservername <nume>
```
Setează numele serverului care va apărea în linkul de vizionare (ex: "Freia [SERVER 2]")
```
[p]showanimesecsettings
```
Afișează setările curente pentru anime

### Configurare Conținut Adult
```
[p]pornrecseturl <URL>
```
Setează URL-ul serverului Jellyfin pentru conținut adult
```
[p]pornrecsetapi <API_KEY>
```
Setează cheia API Jellyfin pentru conținut adult
```
[p]pornrecsettmdbapi <API_KEY>
```
Setează cheia API TMDb pentru conținut adult (opțional, nu este folosită)
```
[p]setpornrecommendationchannel <#canal>
```
Setează canalul unde vor fi trimise recomandările automate
```
[p]setpornservername <nume>
```
Setează numele serverului care va apărea în linkul de vizionare
```
[p]showpornrecsettings
```
Afișează setările curente pentru conținut adult

## Comenzi Utilizatori

### Recomandare Anime
```
[p]recomanda anime
```
Generează o recomandare aleatorie de anime instant

### Recomandare Conținut Adult
```
[p]recomanda porn
```
Generează o recomandare aleatorie de conținut adult instant

## Obținerea cheilor API

### Jellyfin API Key

1. Conectează-te la serverul tău Jellyfin
2. Du-te la **Dashboard** → **API Keys**
3. Click pe **+** pentru a crea o cheie nouă
4. Dă-i un nume (ex: "Discord Bot")
5. Copiază cheia generată

### TMDb API Key (pentru anime)

1. Creează un cont pe [The Movie Database](https://www.themoviedb.org/)
2. Du-te la **Settings** → **API**
3. Solicită o cheie API (alege "Developer")
4. Completează formularul cu informații despre bot
5. Copiază API Key (v3 auth)

## Funcționare

### Recomandări Automate

Botul trimite automat recomandări în fiecare **luni la ora 18:00** în canalele configurate:
- O recomandare de anime (dacă este configurat)
- O recomandare de conținut adult (dacă este configurat)

### Recomandări Manuale

Utilizatorii pot genera recomandări oricând folosind comenzile `.recomanda anime` sau `.recomanda porn`.

### Diferențe între Anime și Conținut Adult

| Caracteristică | Anime | Conținut Adult |
|---------------|-------|----------------|
| Sursa posterelor | TMDb | Jellyfin |
| Sursa descrierilor | TMDb | Jellyfin |
| Traducere automată | ✅ Da | ✅ Da |
| Necesită TMDb API | ✅ Recomandat | ❌ Nu |

## Exemple de Embed-uri

### Anime
- 🎨 Culoare: Albastru
- 🖼️ Poster: De la TMDb (înaltă calitate)
- 📝 Descriere: De la TMDb (tradusă în română)
- ℹ️ Informații: Tip, Gen, Rating, Link server

### Conținut Adult
- 🎨 Culoare: Roșu
- 🖼️ Poster: De la Jellyfin
- 📝 Descriere: De la Jellyfin (tradusă în română)
- ℹ️ Informații: Tip, Gen, Rating, Link server

## Permisiuni Necesare

### Pentru Administratori
- Toate comenzile de configurare necesită permisiunea de **Administrator** sau permisiunea specifică `administrator`

### Pentru Bot
Botul necesită următoarele permisiuni în canalele configurate:
- `Send Messages` - pentru a trimite recomandări
- `Embed Links` - pentru a afișa embed-uri
- `Attach Files` - pentru imagini (opțional)

## Depanare

### Recomandările nu apar
- Verifică dacă botul are permisiunile necesare în canal
- Verifică setările cu `[p]showanimesecsettings` sau `[p]showpornrecsettings`
- Asigură-te că toate câmpurile sunt configurate corect

### Descrierile lipsesc
- Pentru anime: verifică dacă TMDb API key este setat și valid
- Pentru conținut adult: asigură-te că metadata este completă în Jellyfin
- Verifică consolele botului pentru erori de traducere

### Posterele nu apar
- Pentru anime: verifică conexiunea la TMDb
- Pentru conținut adult: asigură-te că item-urile au imagini în Jellyfin
- Verifică dacă Jellyfin API key-ul are permisiunile necesare

### Traducerea nu funcționează
- Verifică conexiunea la internet a botului
- Asigură-te că `deep-translator` este instalat corect
- Verifică consolele pentru erori de la Google Translate

## Suport

Pentru probleme, bug-uri sau sugestii:
- Deschide un issue pe GitHub
- Contactează dezvoltatorul: Drago Prime

## Licență

[Specifică licența aici]

## Changelog

### v1.0.0
- ✨ Lansare inițială
- 🎌 Suport pentru anime cu integrare TMDb
- 🔞 Suport pentru conținut adult cu metadata Jellyfin
- 🌐 Traducere automată în română
- ⏰ Recomandări automate săptămânale
- 🎲 Comenzi manuale pentru recomandări instant

## Credite

- **Autor**: Drago Prime
- **Framework**: [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot)
- **APIs**: [Jellyfin](https://jellyfin.org/), [TMDb](https://www.themoviedb.org/)
- **Traducere**: [deep-translator](https://github.com/nidhaloff/deep-translator)
