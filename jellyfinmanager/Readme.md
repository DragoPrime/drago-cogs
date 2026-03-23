# JellyfinManager - Actualizări Complete

## 📝 Ce s-a adăugat

### 1. Comandă Reset Utilizatori
Am adăugat o nouă comandă pentru ștergerea completă a tuturor înregistrărilor de utilizatori din baza de date a botului.

### 2. Ștergere Automată Utilizatori Fără Login (NOU!)
Plugin-ul verifică acum și utilizatorii care nu s-au conectat niciodată la serverul Jellyfin și îi șterge automat după **7 zile** de la creare.

### 3. Comandă Reactivare Utilizatori (NOU!)
Utilizatorii pot acum să își reactiveze singuri conturile dezactivate folosind comanda `.activeaza`.

## 📋 Lista Completă de Comenzi

### Comenzi pentru Utilizatori
- `.creeaza <server> <username> <parola>` - Creează un cont Jellyfin nou
- `.activeaza <server> <username>` - Reactivează un cont dezactivat (doar propriile conturi)
- `.utilizator <@user sau username>` - Verifică informații despre utilizatori

### Comenzi pentru Administratori
- `.server addserver <nume> <url> <admin> <parola> [rol]` - Adaugă server Jellyfin
- `.server removeserver <nume>` - Elimină un server
- `.server listservers` - Listează serverele configurate
- `.server enable` - Activează comenzile pe serverul Discord
- `.server disable` - Dezactivează comenzile pe serverul Discord
- `.server setrole <server> <rol>` - Setează rol pentru un server
- `.server removerole <server>` - Elimină rolul pentru un server
- `.server setchannel <#canal>` - Setează canalul pentru notificări
- `.server removechannel` - Elimină canalul de notificări
- `.server togglecleanup` - Activează/dezactivează cleanup automat
- `.server checkcleanup` - Execută manual verificarea cleanup (testare)
- `.server resetusers` - Șterge toate înregistrările de utilizatori (IREVERSIBIL)

## 🆕 Funcționalități Noi

### A. Comandă: `.server resetusers`

### Descriere
Această comandă șterge **TOATE** înregistrările de utilizatori din baza de date a botului (tracking-ul local). 

### ⚠️ IMPORTANT
- **NU** șterge utilizatorii de pe serverele Jellyfin propriu-zise
- Șterge doar tracking-ul din baza de date a botului
- **Această acțiune este IREVERSIBILĂ**

### Utilizare

```
.server resetusers
```

### Cum funcționează

1. **Afișare statistici**: Botul va afișa un embed cu:
   - Numărul total de utilizatori Discord trackați
   - Numărul total de conturi Jellyfin
   - Toate datele care vor fi șterse

2. **Cerere confirmare**: Utilizatorul trebuie să scrie exact `CONFIRM DELETE ALL` în 30 de secunde

3. **Execuție**: Dacă se confirmă, botul va:
   - Șterge complet baza de date users
   - Afișa un embed de confirmare cu statisticile ștergerii
   - Loga acțiunea în console

### Permisiuni
- **Doar owner-ul botului** poate folosi această comandă
- Se folosește decorator-ul `@checks.is_owner()`

### Exemplu de Utilizare

```
Admin: .server resetusers

Bot: [Afișează embed de avertizare]
     📊 Ce va fi șters:
     • X utilizatori Discord
     • Y conturi Jellyfin
     • Tot istoricul de tracking
     
     ✅ Pentru a confirma:
     Scrie `CONFIRM DELETE ALL` în următoarele 30 de secunde

Admin: CONFIRM DELETE ALL

Bot: ✅ Reset Complet Efectuat
     Toate înregistrările de utilizatori au fost șterse din baza de date
```

### Cazuri de Timeout

Dacă utilizatorul nu confirmă în 30 de secunde:
```
Bot: ❌ Operațiune anulată - timeout.
```

### Dacă nu există utilizatori

```
Bot: ✅ Nu există utilizatori în baza de date.
```

### B. Ștergere Automată Utilizatori Fără Login

#### Descriere
Plugin-ul verifică automat utilizatorii care nu s-au conectat **niciodată** la serverul Jellyfin și îi șterge după 7 zile de la creare.

#### Cum funcționează

1. **Verificare zilnică**: Task-ul automat verifică toți utilizatorii
2. **Detectare utilizatori fără login**: 
   - Dacă un utilizator nu are istoric de vizionare (LastActivityDate == null)
   - Și nu are LastLoginDate
   - Plugin-ul folosește data creării contului (created_at)
3. **Ștergere după 7 zile**:
   - Dacă au trecut 7+ zile de la creare
   - ȘI utilizatorul nu s-a conectat niciodată
   - Contul este șters automat

#### Reguli de Inactivitate (actualizate)

| Situație | Perioadă | Acțiune |
|----------|----------|---------|
| **Utilizator nou fără login** | 7 zile | 🚫 **Șters** (niciodată conectat) |
| Utilizator inactiv | 30 zile | 🟡 **Dezactivat** |
| Utilizator dezactivat | 60 zile (total) | 🗑️ **Șters** (inactivitate prelungită) |

#### Notificări

Când un utilizator este șters pentru că nu s-a conectat niciodată, primește:

**DM Personal:**
```
🚫 Contul tău Jellyfin a fost șters (niciodată conectat)

🖥️ Server: [nume_server]
👤 Username Jellyfin: [username]
📅 Creat la: [data]
⏰ Zile de la creare: 7+

🚫 Cont șters - Niciodată folosit
Contul tău a fost șters deoarece nu te-ai conectat 
la el în 7 zile de la creare.

Dacă ai nevoie de un nou cont, te rog contactează 
administratorii.
```

**În canalul de notificări:**
```
🚫 Utilizator șters (niciodată conectat)

👤 Utilizator Discord: @Username
🎬 Utilizator Jellyfin: username_jellyfin
🖥️ Server: server_name
📅 Creat la: [data]
⏰ Zile de la creare: 7

ℹ️ Notă: Utilizatorul nu s-a conectat niciodată 
(șters după 7 zile)
```

#### Avantaje

✅ **Curățare automată**: Elimină conturile neutilizate rapid
✅ **Economie de resurse**: Nu ocupă spațiu cu conturi inactive
✅ **Transparență**: Utilizatorii sunt notificați
✅ **Flexibilitate**: Pot crea un cont nou dacă au nevoie

### C. Cazuri de Utilizare

#### Caz 1: Utilizator creează 2 conturi, dar folosește doar unul

```
Ziua 0: User creează "username1" și "username2"
Ziua 0: User se conectează la "username1" ✅
Ziua 0: User NU se conectează la "username2" ❌

Ziua 7: 
  - "username1" rămâne activ (are activitate)
  - "username2" este șters automat (7 zile fără login)
  - User primește notificare despre "username2"
```

#### Caz 2: Utilizator creează cont dar uită de el

```
Ziua 0: User creează "test_account"
Ziua 0-6: User nu se conectează niciodată

Ziua 7:
  - "test_account" este șters automat
  - User primește DM cu notificarea
  - Admin primește notificare în canal
```

### D. Comandă: `.activeaza` - Reactivare Utilizatori Dezactivați

#### Descriere
Permite utilizatorilor să își reactiveze singuri conturile Jellyfin care au fost dezactivate din cauza inactivității.

#### Utilizare

```
.activeaza <nume_server> <nume_utilizator_jellyfin>
```

**Exemple:**
```
.activeaza server1 john123
.activeaza jellyfin_main my_username
```

**Alias-uri:** `.reactivare`, `.enable`

#### Cum funcționează

1. **Verificare permisiuni**: 
   - Doar proprietarul contului Discord poate reactiva propriile conturi
   - Nu poți reactiva conturile altora

2. **Verificare status**:
   - ✅ Contul trebuie să fie în status "disabled"
   - ❌ Conturile "active" nu pot fi reactivate (sunt deja active)
   - ❌ Conturile "deleted" nu pot fi reactivate (trebuie creat cont nou)

3. **Procesare**:
   - Botul se conectează la serverul Jellyfin
   - Schimbă IsDisabled de la True la False
   - Actualizează status-ul în baza de date
   - Trimite confirmare

#### Exemple de Utilizare

**Succes:**
```
User: .activeaza server1 myuser

Bot: 🔄 Reactivez utilizatorul myuser pe serverul server1...

Bot: ✅ Utilizator Reactivat cu Succes!
     
     🖥️ Server: server1
     👤 Utilizator: myuser
     📊 Status: 🟢 Activ
     🌐 URL Server: http://jellyfin.example.com
     
     ℹ️ Notă:
     Contul tău este acum activ! Poți să te conectezi și să vizionezi conținut.
     Atenție: Contul va fi din nou dezactivat după 30 de zile de inactivitate.
```

**Erori posibile:**

```
# Cont deja activ
❌ Utilizatorul myuser este deja activ!

# Cont șters
❌ Utilizatorul myuser a fost șters și nu poate fi reactivat.
Te rog creează un cont nou cu `.creeaza server1 <nume_nou> <parola>`

# Utilizator inexistent
❌ Nu ai un utilizator cu numele myuser pe serverul server1.
Utilizatorii tăi pe acest server: user1, user2

# Server inexistent
❌ Serverul server2 nu există. Servere disponibile: server1, jellyfin_main
```

#### Securitate

✅ **Protecție**: Utilizatorii pot reactiva doar propriile conturi
✅ **Validare**: Verifică toate condițiile înainte de reactivare
✅ **Logging**: Toate reactivările sunt înregistrate în logs
✅ **Feedback**: Utilizatorul primește confirmări clare

#### Integrare cu Notificări

Când un cont este dezactivat, utilizatorul primește în DM instrucțiuni clare:

```
⚠️ Atenție
Contul tău a fost dezactivat din cauza inactivității. 
Va fi șters permanent în 30 de zile dacă nu este folosit.

Cum îl reactivezi:
Folosește comanda: .activeaza server1 myuser
sau loghează-te și vizionează ceva pentru reactivare automată!
```

## 🆕 Comandă: `.server resetusers`

## 📋 Instalare

1. Copiază directorul `jellyfinmanager` în directorul de cog-uri al botului tău Red
2. Reîncarcă cog-ul:
   ```
   [p]reload jellyfinmanager
   ```
   SAU
   ```
   [p]unload jellyfinmanager
   [p]load jellyfinmanager
   ```

## 🔧 Structura Fișierelor

```
jellyfinmanager/
├── __init__.py          # Fișier de inițializare
├── info.json            # Informații despre cog
└── jellyfinmanager.py   # Codul principal (actualizat cu resetusers)
```

## 📊 Logging

Comanda va loga următoarele informații:
```python
log.info(f"Reset complet utilizatori efectuat de {ctx.author} - {total_users} conturi șterse")
```

## ⚙️ Implementare Tehnică

### Ștergere Utilizatori Fără Login

```python
# Verificare în _check_inactive_users()
if not last_activity:
    # Utilizatorul nu are istoric de vizionare
    created_at = datetime.fromisoformat(user_data.get("created_at"))
    days_since_creation = (now - created_at).days
    
    # Dacă au trecut 7+ zile și nu s-a conectat niciodată
    if created_at <= seven_days_ago and current_status != "deleted":
        # Șterge utilizatorul
        await self._delete_jellyfin_user(server_url, token, jellyfin_id)
        
        # Marchează ca șters cu motiv special
        user_data["status"] = "deleted"
        user_data["deletion_reason"] = "never_logged_in"
        
        # Trimite notificare specială
        await self._send_cleanup_notification(
            server_name, jellyfin_username, discord_user_id, 
            "deleted_no_login", created_at
        )
```

### Comandă Reset

Comanda folosește:
- `@server.command(name="resetusers")` - Subcomandă în grupul server
- `@checks.is_owner()` - Restricție de permisiuni
- `MessagePredicate` pentru validarea input-ului
- `asyncio.TimeoutError` pentru timeout de 30 secunde
- `discord.Embed` pentru afișare frumoasă

## 🛡️ Măsuri de Siguranță

### Pentru Comanda Reset
1. **Dubla confirmare**: Utilizatorul trebuie să scrie exact `CONFIRM DELETE ALL`
2. **Timeout**: Doar 30 de secunde pentru confirmare
3. **Permisiuni stricte**: Doar owner-ul botului
4. **Avertizări clare**: Embed roșu cu toate detaliile
5. **Logging**: Toate acțiunile sunt logate

### Pentru Ștergere Automată
1. **Perioadă de grație**: 7 zile pentru utilizatori fără login
2. **Verificare precisă**: Doar dacă nu există niciun istoric de activitate
3. **Notificări**: Utilizatorii primesc DM înainte de ștergere
4. **Logging detaliat**: Toate acțiunile sunt înregistrate
5. **Nu afectează utilizatorii activi**: Doar cei fără login sunt verificați

## 🔄 Flux Complet de Verificare și Acțiuni Utilizator

```
Verificare Zilnică
    ↓
Pentru fiecare utilizator:
    ↓
Are last_activity?
    ├─ NU → Verifică created_at
    │        ↓
    │    created_at > 7 zile?
    │        ├─ DA → 🚫 ȘTERGE (never_logged_in)
    │        └─ NU → ✅ Păstrează
    │
    └─ DA → Calculează zile de inactivitate
             ↓
         > 60 zile?
             ├─ DA → 🗑️ ȘTERGE (inactivitate)
             └─ NU → Verifică > 30 zile?
                      ├─ DA → 🟡 DEZACTIVEAZĂ
                      │        ↓
                      │   Trimite DM cu instrucțiuni
                      │   User poate folosi: .activeaza
                      │        ↓
                      │   User execută .activeaza?
                      │        ├─ DA → 🟢 REACTIVAT
                      │        └─ NU → Rămâne dezactivat
                      │
                      └─ NU → ✅ Păstrează
```

## 📝 Note Finale

### Comandă Reset
- Serverele Jellyfin rămân neschimbate
- Utilizatorii de pe Jellyfin rămân activi
- Se șterge doar tracking-ul local din baza de date a botului
- Ideal pentru debugging sau restart complet al sistemului de tracking

### Ștergere Automată Utilizatori Fără Login
- ✅ Utilizatorii sunt notificați prin DM
- ✅ Adminii primesc notificări în canal
- ✅ Conturile de pe Jellyfin sunt șterse efectiv
- ✅ Tracking-ul local este actualizat
- ⚠️ Utilizatorii pot crea un cont nou dacă au nevoie
- ⚠️ Verificarea rulează automat la fiecare 24h

## 🎯 Beneficii

1. **Curățare automată**: Elimină conturile create dar neutilizate
2. **Economie de resurse**: Nu ocupă spațiu pe server
3. **Management simplificat**: Administratorii nu trebuie să șteargă manual
4. **Transparență**: Toată lumea este informată
5. **Flexibilitate**: Utilizatorii pot crea conturi noi când au nevoie
6. **Self-service**: Utilizatorii pot reactiva propriile conturi fără ajutorul adminilor

## 📖 Scenarii Complete de Utilizare

### Scenariu 1: Utilizator Inactiv - Reactivare Reușită

```
Ziua 0: John creează cont "john123" pe server1
Ziua 1-29: John vizionează filme regulat
Ziua 30-59: John pleacă în vacanță, nu se conectează

Ziua 60:
  🟡 Botul dezactivează automat "john123"
  📧 John primește DM:
     "Contul tău a fost dezactivat. 
      Folosește: .activeaza server1 john123"

Ziua 61:
  John: .activeaza server1 john123
  Bot: ✅ Utilizator Reactivat cu Succes!
  🟢 Contul "john123" este din nou activ

Ziua 62+:
  John continuă să folosească contul normal
```

### Scenariu 2: Utilizator cu Multiple Conturi

```
Mary creează:
  - "mary_films" pe server1 (îl folosește)
  - "mary_test" pe server1 (nu se conectează niciodată)

Ziua 7:
  🚫 "mary_test" șters automat (niciodată conectat)
  📧 Mary primește notificare
  ✅ "mary_films" rămâne activ

Ziua 30+:
  Mary nu mai folosește "mary_films"
  
Ziua 60:
  🟡 "mary_films" dezactivat
  
Ziua 61:
  Mary: .activeaza server1 mary_films
  Bot: ✅ Reactivat!
```

### Scenariu 3: Utilizator Uită Complet de Cont

```
Bob creează "bob_movies"
Nu se conectează niciodată

Ziua 60:
  🟡 Dezactivat automat
  📧 Bob primește DM cu instrucțiuni
  Bob ignoră mesajul

Ziua 90:
  🗑️ "bob_movies" șters definitiv
  📧 Bob primește notificare de ștergere
  
Ziua 91:
  Bob vrea să revină
  Bob: .activeaza server1 bob_movies
  Bot: ❌ Contul a fost șters, creează unul nou
  
  Bob: .creeaza server1 bob_new parola123
  Bot: ✅ Cont nou creat!
```

## ⚡ Quick Start

1. Instalează/actualizează plugin-ul
2. Configurează serverele Jellyfin: `.server addserver`
3. Activează comenzile: `.server enable`
4. Setează canalul de notificări: `.server setchannel #canal`
5. Verifică cleanup-ul: `.server checkcleanup` (testare)
6. Plugin-ul va rula automat verificarea la fiecare 24h

## 🐛 Troubleshooting

### Utilizatorii nu sunt șterși automat
- Verifică că cleanup-ul este activat: `.server listservers`
- Verifică logs pentru erori
- Testează manual cu `.server checkcleanup`

### Notificările nu ajung
- Verifică canalul de notificări: `.server setchannel #canal`
- Verifică permisiunile botului în canal
- Verifică că utilizatorii au DM-urile deschise

### Vreau să schimb perioada de 7 zile
- Modifică în cod linia: `seven_days_ago = now - timedelta(days=7)`
- Schimbă `days=7` cu valoarea dorită
- Reîncarcă cog-ul
