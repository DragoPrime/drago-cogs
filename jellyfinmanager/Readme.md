# JellyfinManager - Actualizare cu Comandă Reset Utilizatori

## 📝 Ce s-a adăugat

Am adăugat o nouă comandă pentru ștergerea completă a tuturor înregistrărilor de utilizatori din baza de date a botului.

## 🆕 Comandă Nouă: `.server resetusers`

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

Comanda folosește:
- `@server.command(name="resetusers")` - Subcomandă în grupul server
- `@checks.is_owner()` - Restricție de permisiuni
- `MessagePredicate` pentru validarea input-ului
- `asyncio.TimeoutError` pentru timeout de 30 secunde
- `discord.Embed` pentru afișare frumoasă

## 🛡️ Măsuri de Siguranță

1. **Dubla confirmare**: Utilizatorul trebuie să scrie exact `CONFIRM DELETE ALL`
2. **Timeout**: Doar 30 de secunde pentru confirmare
3. **Permisiuni stricte**: Doar owner-ul botului
4. **Avertizări clare**: Embed roșu cu toate detaliile
5. **Logging**: Toate acțiunile sunt logate

## 📝 Note Finale

- Serverele Jellyfin rămân neschimbate
- Utilizatorii de pe Jellyfin rămân activi
- Se șterge doar tracking-ul local din baza de date a botului
- Ideal pentru debugging sau restart complet al sistemului de tracking
