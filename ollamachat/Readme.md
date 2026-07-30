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
   (Recomandare: pentru română, modele precum `llama3`, `gemma2` sau `mistral` merg relativ bine;
   calitatea în limba română variază de la model la model — testează câteva.)
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
