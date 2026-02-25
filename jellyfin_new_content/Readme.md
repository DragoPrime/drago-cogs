# 🎬 JellyfinNewContent

Un cog pentru **Red Discord Bot** care monitorizează mai multe servere **Jellyfin** și anunță automat în Discord filmele și serialele nou adăugate.

## ✨ Funcționalități

- 📡 Suport pentru **mai multe servere Jellyfin** simultan
- 🖼️ Integrare cu **TMDb** pentru postere și descrieri detaliate
- 🌍 **Traducere automată** în română prin Google Translate (`deep-translator`)
- ⏱️ Verificare periodică configurabilă (implicit la fiecare 6 ore)
- 🛡️ Limită anti-spam: maxim 20 anunțuri per verificare
- 🔒 Ștergere automată a mesajelor cu chei API sensibile

---

## 📦 Instalare

```bash
[p]repo add <nume-repo> <url-repo>
[p]cog install <nume-repo> jellyfin_new_content
[p]load jellyfin_new_content
```

**Dependințe instalate automat:** `aiohttp`, `deep-translator`

> `[p]` reprezintă prefixul botului tău.

---

## ⚙️ Configurare rapidă

```
1. [p]newcontent addserver <NUME>
2. [p]newcontent seturl <NUME> <URL>
3. [p]newcontent setapi <NUME> <API_KEY>
4. [p]newcontent setchannel <NUME> #canal
5. (opțional) [p]newcontent settmdb <NUME> <TMDB_API_KEY>
6. [p]newcontent forceinit <NUME>
```

---

## 📋 Referință comenzi

Toate comenzile încep cu `[p]newcontent`.

---

### 🖥️ Gestionare servere

#### `addserver <NUME>`
Adaugă un server Jellyfin nou cu numele specificat. După adăugare, trebuie configurat cu comenzile de mai jos.

**Exemplu:**
```
[p]newcontent addserver ServerulMeu
```

---

#### `removeserver <NUME>`
Șterge un server Jellyfin și toate configurațiile asociate acestuia.

**Exemplu:**
```
[p]newcontent removeserver ServerulMeu
```

---

#### `listservers`
Afișează lista tuturor serverelor configurate, împreună cu statusul fiecăruia (complet configurat / configurare incompletă), canalul de anunțuri și dacă a fost inițializat.

**Exemplu:**
```
[p]newcontent listservers
```

---

#### `serverinfo <NUME>`
Afișează informații detaliate despre un server: URL, status chei API, canal de anunțuri, ultima verificare și statusul inițializării.

**Exemplu:**
```
[p]newcontent serverinfo ServerulMeu
```

---

### 🔧 Configurare server

#### `seturl <NUME> <URL>`
Setează URL-ul de bază al serverului Jellyfin. Nu include `/` la finalul URL-ului (va fi eliminat automat).

**Exemplu:**
```
[p]newcontent seturl ServerulMeu https://jellyfin.exemplu.ro
```

---

#### `setapi <NUME> <API_KEY>`
Setează cheia API Jellyfin pentru serverul specificat. Mesajul cu cheia API este **șters automat** după salvare pentru securitate.

> 💡 Cheia API se găsește în Jellyfin la: **Dashboard → API Keys**

**Exemplu:**
```
[p]newcontent setapi ServerulMeu abc123xyz456
```

---

#### `settmdb <NUME> <API_KEY>`
Setează cheia API TMDb pentru obținerea posterelor și descrierilor. Opțional, dar recomandat pentru anunțuri mai frumoase. Mesajul este **șters automat** după salvare.

> 💡 Cheia API TMDb se obține gratuit de pe [themoviedb.org](https://www.themoviedb.org/settings/api)

**Exemplu:**
```
[p]newcontent settmdb ServerulMeu tmdb_key_123
```

---

#### `setchannel <NUME> <#CANAL>`
Setează canalul Discord în care vor fi postate anunțurile pentru serverul specificat.

**Exemplu:**
```
[p]newcontent setchannel ServerulMeu #filme-noi
```

---

### 🌍 Configurare traducere

#### `toggletranslation`
Activează sau dezactivează traducerea automată a descrierilor în română folosind Google Translate. Setare globală (afectează toate serverele din guild).

> ℹ️ Textele care conțin deja caractere românești (ă, â, î, ș, ț) nu vor fi retraduse.

**Exemplu:**
```
[p]newcontent toggletranslation
```

---

### ⚙️ Configurare globală

#### `setinterval <ORE>`
Setează intervalul de timp (în ore) între verificările automate de conținut nou. Valoarea minimă este **1 oră**.

**Exemplu:**
```
[p]newcontent setinterval 12
```

---

#### `settings`
Afișează setările globale curente ale plugin-ului: intervalul de verificare, statusul traducerii automate, numărul de servere configurate și limita de anunțuri per verificare.

**Exemplu:**
```
[p]newcontent settings
```

---

### 🛠️ Utilitare

#### `check <NUME>`
Declanșează manual o verificare de conținut nou pentru serverul specificat, fără a aștepta intervalul automat. Util pentru testare.

**Exemplu:**
```
[p]newcontent check ServerulMeu
```

---

#### `reset <NUME>`
Resetează timestamp-ul ultimei verificări și marcajul de inițializare pentru un server. La următoarea verificare automată, serverul va fi re-inițializat fără a anunța conținutul existent.

**Exemplu:**
```
[p]newcontent reset ServerulMeu
```

---

#### `forceinit <NUME>`
Forțează inițializarea unui server setând timestamp-ul la momentul curent, fără a anunța conținutul deja existent pe server. Folosește această comandă după configurarea inițială pentru a evita spam-ul cu tot conținutul existent.

**Exemplu:**
```
[p]newcontent forceinit ServerulMeu
```

---

#### `debug <NUME>`
Rulează o verificare completă și afișează **fiecare pas în timp real direct în canalul Discord** unde este tastată comanda. Util când `check` nu anunță nimic și vrei să înțelegi de ce.

Informațiile afișate includ:
- Timestamp-ul ultimei verificări (de la care se caută conținut nou)
- URL-ul request-ului trimis către Jellyfin și codul HTTP primit
- Numărul total de iteme returnate de Jellyfin
- Primele iteme din răspuns (titlu, tip, dată adăugare)
- Fiecare item nou detectat sau motivul pentru care a fost ignorat
- Sumar final: câte iteme noi, câte mai vechi, câte cu erori de dată

**Exemplu de output:**
```
[ServerulMeu] 🔍 Caut conținut adăugat după: 24.02.2026 21:00:00
[ServerulMeu] 📡 Request către Jellyfin (din 2026-02-24): `.../Items?...`
[ServerulMeu] 📶 Răspuns Jellyfin: HTTP 200
[ServerulMeu] 📦 Total iteme returnate de Jellyfin: 3
[ServerulMeu] 🔎 Primele iteme: `Attack on Titan (Series) — 2026-02-25T00:30:00`
[ServerulMeu] ✅ NOU: `Attack on Titan (Series)` — adăugat la 2026-02-25T00:30:00
[ServerulMeu] 📊 Rezultat: 1 noi, 2 mai vechi, 0 cu erori de dată.
```

> ⚠️ Folosește această comandă într-un canal privat sau de administrare — afișează informații tehnice despre server.

**Exemplu:**
```
[p]newcontent debug ServerulMeu
```

---

## 📢 Exemplu anunț

Când un film sau serial nou este adăugat pe Jellyfin, botul va posta un embed similar cu:

```
🎬 Film nou adăugat pe ServerulMeu:

Interstellar (2014)
Când o echipă de exploratori călătorește printr-o gaură de vierme...

Tip: Film          Genuri: SF, Aventură, Dramă          Rating: ⭐ 8.6
Vizionare Online: [ServerulMeu](https://jellyfin.exemplu.ro/...)
Adăugat: 23.02.2026 14:30
```

---

## 🔑 Permisiuni necesare

Toate comenzile necesită permisiunea de **Administrator** sau rolul de **Admin** pe serverul Discord.

Botul are nevoie de permisiunile:
- `Send Messages` — pentru a posta anunțurile
- `Embed Links` — pentru embed-uri cu poster și detalii
- `Manage Messages` — pentru ștergerea mesajelor cu chei API *(opțional, dar recomandat)*

---

## 📝 Note

- Prima rulare după `addserver` nu va anunța nimic — folosește `forceinit` pentru a marca conținutul existent ca văzut.
- Dacă TMDb nu este configurat, anunțurile vor fi postate fără poster.
- Maxim **20 de anunțuri** sunt trimise per verificare pentru a evita spam-ul.
- Cheile API sunt stocate în configurația Red Bot și nu sunt vizibile utilizatorilor obișnuiți.

---

## 👤 Autor

**Drago Prime**

---

## 📄 Licență

Distribuie și modifică liber. Nicio garanție implicită.
