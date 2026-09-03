# OllamaChat — cog pentru Red Discord Bot 3.5

Un cog care conectează botul tău Red la un model AI local rulat prin **Ollama**.
Botul poate:

- să întâmpine automat membrii noi cu mesaje generate de AI, pe un canal ales de tine;
- să discute ocazional (probabilistic, cu cooldown) pe un canal ales de tine;
- să vorbească în limba română;
- să aibă o **personalitate** complet configurabilă de tine.

Tot ce se salvează este configurația (URL Ollama, model, personalitate, canale, șanse).
Istoricul scurt de conversație folosit ca și context se ține doar în memorie (RAM) și se pierde la restart.

## Cerințe

1. **Ollama** trebuie să ruleze undeva accesibil botului (implicit `http://localhost:11434`).
   Instalare: https://ollama.com
2. Un model descărcat în Ollama, de exemplu:
   ```bash
   ollama pull llama3
   ```
   (Recomandare: pentru română, modele precum `llama3`, `gemma2`, `mistral` sau `qwen3` merg relativ bine;
   calitatea în limba română variază de la model la model — testează câteva.)

   **Notă pentru modele cu "thinking mode" (ex: `qwen3`, `deepseek-r1`):** cog-ul dezactivează
   automat acest mod (`think: false`) pentru răspunsuri rapide și curate, potrivite pentru chat live.
   Îl poți reactiva oricând cu `[p]ollamaset gandire`, dacă preferi răspunsuri mai atent raționate
   (dar mai lente).
3. Red Discord Bot 3.5+ deja instalat și funcțional.

## Instalare

1. Copiază folderul `ollamachat` în directorul de cog-uri custom al instanței tale Red
   (de obicei acolo unde ai adăugat alte cog-uri locale, via `[p]addpath` sau similar).
   Cel mai simplu: folosește un repo local sau plasează folderul direct în
   `data/<instance_name>/cogs/CogManager/cogs/` — sau folosește:
   ```
   [p]addpath /calea/catre/folderul/care/contine/ollamachat
   ```
2. Încarcă cog-ul:
   ```
   [p]load ollamachat
   ```

## Configurare rapidă

```
[p]ollamaset url http://localhost:11434
[p]ollamaset model llama3
[p]ollamaset personalitate O personalitate scurtă, prietenoasă, glumeață, care vorbește românește.
[p]ollamaset canalbunvenit #bun-venit
[p]ollamaset canalchat #general
[p]ollamaset sansa 15
[p]ollamaset cooldown 20
```

Vezi configurația curentă oricând cu:
```
[p]ollamaset setari
```

Testează fără să aștepți un membru nou / un mesaj norocos:
```
[p]ollamaset testbunvenit
[p]ollamaset testchat Salut, ce mai faceți?
```

## Integrare Jellyfin

Botul poate căuta live pe serverele tale Jellyfin și include rezultatele relevante drept
context pentru AI, ca să răspundă corect despre ce titluri există — fără să inventeze nimic.
Când găsește un titlu, AI-ul poate include și adresa serverului Jellyfin respectiv în răspuns,
ca utilizatorul să știe direct unde să-l acceseze.

**Extragere inteligentă a termenului de căutare:** botul nu trimite întreaga propoziție a
utilizatorului către Jellyfin (rareori s-ar potrivi cu ceva). În schimb, încearcă, în ordine:
text între ghilimele, apoi secvențe de cuvinte cu majusculă (titluri/nume probabile, ex. "Solo
Leveling" dintr-o întrebare mai lungă), și abia la final propoziția întreagă, ca ultimă
variantă. Se oprește la primul termen care găsește rezultate.

### Cum obții o cheie API Jellyfin

În interfața web Jellyfin: **Dashboard → API Keys → +** (creează o cheie nouă, dă-i un nume).

### Configurare

```
[p]ollamaset jellyfin add Anime https://jellyfin-anime.exemplu.ro:8096 CHEIE_API false Serverul cu anime si desene
[p]ollamaset jellyfin add Adult https://jellyfin-adult.exemplu.ro:8096 CHEIE_API true Continut pentru adulti
[p]ollamaset jellyfin list
```

Parametrii comenzii `add`: `<nume> <url> <cheie_api> <continut_adult:true/false> [descriere]`

**Important:** botul șterge automat mesajul tău după ce salvează serverul (ca să nu rămână
cheia API vizibilă în chat), dar asigură-te oricum că rulezi comanda într-un canal privat sau
că ai permisiunile potrivite.

**Protecție conținut adult:** orice server marcat cu `true` la `continut_adult` este folosit de
AI **doar** atunci când cineva întreabă dintr-un canal Discord marcat ca **NSFW** (Server
Settings → canal → Edit Channel → Age-Restricted Channel). În canale normale, acel server e
complet ignorat de căutare — botul nu va menționa nici măcar că există.

**Notă de securitate:** botul include adresa (URL-ul) serverului Jellyfin în răspunsuri, ca
utilizatorii să știe direct unde să acceseze un titlu. Asta înseamnă că oricine poate citi
canalul respectiv va vedea acea adresă, chiar dacă nu are cont pe Jellyfin — asigură-te că
serverele tale sunt oricum protejate prin autentificare/rețea (VPN, reverse proxy cu login,
etc.) și nu te baza doar pe faptul că adresa nu e cunoscută public.

### Alte comenzi Jellyfin

| Comandă | Descriere |
|---|---|
| `jellyfin add <nume> <url> <cheie> <adult:true/false> [descriere]` | Adaugă un server |
| `jellyfin remove <nume>` | Șterge un server |
| `jellyfin list` | Listează serverele configurate (fără cheile API) |
| `jellyfin test <nume> <cautare>` | Testează direct o căutare pe un server |
| `jellyfin limita <numar>` | Câte rezultate se caută per server (implicit 6) |
| `jellyfin toggle` | Activează/dezactivează toată integrarea Jellyfin |

**Titluri cu mai multe variante (sezoane, filme separate):** căutarea Jellyfin întoarce toate
potrivirile găsite (până la limita setată), cu an și tip (Serie/Film). AI-ul este instruit să
le enumere pe toate, nu să aleagă el una singură — dacă ai serii cu multe sezoane sau filme
separate, poate fi util să mărești limita cu `jellyfin limita`.

## Toate comenzile (`[p]ollamaset ...`)

| Comandă | Descriere |
|---|---|
| `url <adresa>` | Adresa serverului Ollama |
| `model <nume>` | Modelul folosit (ex: `llama3`) |
| `personalitate <text>` | Descrierea personalității AI-ului |
| `canalbunvenit [#canal]` | Canalul pentru mesaje de bun venit (fără argument = dezactivează) |
| `canalchat [#canal]` | Canalul unde botul discută ocazional (fără argument = dezactivează) |
| `sansa <1-100>` | Șansa (%) ca botul să răspundă la un mesaj din canalul de chat |
| `cooldown <secunde>` | Timp minim între două răspunsuri automate |
| `istoric <1-20>` | Câte mesaje anterioare ține minte AI-ul drept context |
| `gandire` | Activează/dezactivează modul "thinking" pentru modele care îl suportă (ex: qwen3). Implicit dezactivat, pentru răspunsuri rapide. |
| `toggle` | Activează/dezactivează chat-ul ocazional |
| `togglebunvenit` | Activează/dezactivează mesajele de bun venit |
| `testbunvenit` | Generează un mesaj de bun venit de test |
| `testchat <mesaj>` | Testează un răspuns AI pornind de la un mesaj dat de tine |
| `setari` | Afișează configurația curentă |

Toate comenzile necesită permisiunea `manage_guild` (sau admin).

## Note

- Dacă Ollama nu răspunde (nu rulează, URL greșit, timeout), cog-ul eșuează silențios la mesajele
  de bun venit și afișează eroarea la comenzile de test, fără să blocheze restul botului.
- Cog-ul ignoră mesajele care sunt de fapt comenzi către bot (nu răspunde AI la ele).
- Contextul de conversație (istoricul) e per canal și e ținut doar în memorie, nu pe disc.
