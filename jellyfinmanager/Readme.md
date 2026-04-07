# JellyfinManager - Plugin Simplificat pentru Cleanup Automat

## 📝 Modificări Finale

Plugin-ul a fost simplificat pentru a gestiona automat utilizatorii inactivi fără intervenție manuală.

### ✅ Ce s-a păstrat:
- Ștergere automată după **90 de zile** de inactivitate
- Ștergere automată după **7 zile** pentru utilizatori care nu s-au conectat niciodată
- Notificări prin DM și canal pentru utilizatori șterși
- Tracking complet al utilizatorilor
- Eliminare automată a rolurilor când utilizatorul părăsește serverul Discord

### ❌ Ce s-a eliminat:
- Funcționalitatea de dezactivare (30 zile)
- Comanda `.activeaza` pentru reactivare
- Mesajele de notificare pentru dezactivare
- Logica complexă de stări (activ/dezactivat/șters)

## 🎯 Sistem Simplificat

### Reguli de Inactivitate

| Situație | Perioadă | Acțiune |
|----------|----------|---------|
| **Utilizator nou fără login** | 7 zile | 🚫 **Șters** (niciodată conectat) |
| **Utilizator inactiv** | 90 zile | 🗑️ **Șters** (inactivitate prelungită) |

### Flux Complet

```
Verificare Zilnică (24h)
    ↓
Pentru fiecare utilizator:
    ↓
Are last_activity?
    ├─ NU → Verifică created_at
    │        ↓
    │    > 7 zile de la creare?
    │        ├─ DA → 🚫 ȘTERGE (never_logged_in)
    │        └─ NU → ✅ Păstrează
    │
    └─ DA → Calculează zile de inactivitate
             ↓
         > 90 zile?
             ├─ DA → 🗑️ ȘTERGE
             └─ NU → ✅ Păstrează
```

## 📋 Comenzi Disponibile

### Comenzi pentru Utilizatori
- `.creeaza <server> <username> <parola>` - Creează un cont Jellyfin nou
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

## 🔔 Notificări

### Notificare Ștergere (90 zile inactivitate)

**DM Privat:**
```
🗑️ Contul tău Jellyfin a fost șters

🖥️ Server: server_name
👤 Username Jellyfin: username
⏰ Zile de inactivitate: 90+
📅 Ultima activitate: DD.MM.YYYY HH:MM

🗑️ Cont șters
Contul tău a fost șters definitiv din cauza inactivității 
prelungite (90+ zile). Dacă dorești un nou cont, contactează 
administratorii.
```

**În canal:**
```
🗑️ Utilizator șters

👤 Utilizator Discord: @Username
🎬 Utilizator Jellyfin: username
🖥️ Server: server_name
📅 Ultima activitate: DD.MM.YYYY HH:MM
⏰ Zile inactive: 90+
```

### Notificare Ștergere (7 zile fără login)

**DM Privat:**
```
🚫 Contul tău Jellyfin a fost șters (niciodată conectat)

🖥️ Server: server_name
👤 Username Jellyfin: username
📅 Creat la: DD.MM.YYYY HH:MM
⏰ Zile de la creare: 7+

🚫 Cont șters - Niciodată folosit
Contul tău a fost șters deoarece nu te-ai conectat 
la el în 7 zile de la creare.

Dacă ai nevoie de un nou cont, contactează administratorii.
```

**În canal:**
```
🚫 Utilizator șters (niciodată conectat)

👤 Utilizator Discord: @Username
🎬 Utilizator Jellyfin: username
🖥️ Server: server_name
📅 Creat la: DD.MM.YYYY HH:MM
⏰ Zile de la creare: 7

ℹ️ Notă: Utilizatorul nu s-a conectat niciodată 
(șters după 7 zile)
```

## 🎭 Gestionarea Rolurilor

### Eliminare Automată când Nu Mai Există Conturi Active

Plugin-ul elimină automat rolurile Discord când un utilizator **nu mai are niciun cont activ** pe un server Jellyfin:

**Când se elimină rolul:**
1. ✅ Un utilizator are conturi pe "server1" Jellyfin
2. ✅ Utilizatorul primește rolul `@JellyfinServer1` când creează primul cont
3. ⏰ Toate conturile utilizatorului pe "server1" sunt șterse (inactivitate/fără login)
4. 🎭 **Rolul `@JellyfinServer1` este eliminat automat**

**Exemplu:**
```
User creează 2 conturi pe server1:
  - "username1" → activ
  - "username2" → activ
  Rol: ✅ @JellyfinServer1

Ziua 7: "username2" șters (fără login)
  Conturi rămase: "username1" (activ)
  Rol: ✅ Păstrat (mai are 1 cont activ)

Ziua 90: "username1" șters (inactivitate)
  Conturi rămase: 0 active
  Rol: 🎭 Eliminat automat!
```

**Logging:**
```
Verificare roluri pentru user 123456789 pe server1
  Conturi active: 0 din 2
  ⚠️ Nu mai are conturi active, eliminare rol...
  ✅ Rol JellyfinServer1 eliminat din My Discord Server
```

### Când Utilizatorul Părăsește Serverul Discord

Când un utilizator părăsește complet serverul Discord:
1. ✅ Discord elimină **automat toate rolurile** (comportament nativ)
2. ✅ Conturile Jellyfin rămân active pe server
3. ✅ Event-ul este logat pentru audit

**Logging:**
```
=== MEMBRU PĂRĂSEȘTE SERVERUL ===
Utilizator: John#1234 (ID: 123456789)
Guild: My Discord Server
Discord va elimina automat toate rolurile
```

## 📊 Scenarii de Utilizare

### Scenariu 1: Utilizator Activ

```
Ziua 0: User creează "username" și se conectează
Ziua 1-89: User vizionează filme regulat

Status: ✅ Cont activ, nicio acțiune
```

### Scenariu 2: Utilizator Creează Cont dar Nu-l Folosește

```
Ziua 0: User creează "test_account"
Ziua 0-6: User nu se conectează niciodată

Ziua 7:
  🚫 "test_account" șters automat
  📧 User primește DM
  📢 Admin primește notificare în canal
```

### Scenariu 3: Utilizator Inactiv Prelungit

```
Ziua 0-30: User folosește contul normal
Ziua 31-89: User nu se mai conectează

Ziua 90:
  🗑️ Cont șters automat
  📧 User primește DM
  📢 Admin primește notificare în canal
```

### Scenariu 4: Utilizator Fără Conturi Active

```
User are 2 conturi pe server1:
  - "account1" → Activ, rol @JellyfinServer1 atribuit
  - "account2" → Activ

Ziua 90: "account1" șters (inactivitate)
  Conturi active: 1 ("account2")
  Rol: ✅ Păstrat

Ziua 91: "account2" șters (inactivitate)
  Conturi active: 0
  Rol: 🎭 @JellyfinServer1 eliminat automat
  
  📝 Log: "Nu mai are conturi active, eliminare rol..."
```

### Scenariu 5: Utilizator Părăsește Serverul Discord

```
User are cont Jellyfin cu rol @JellyfinServer1
User părăsește serverul Discord

Automat:
  🎭 Discord elimină toate rolurile (inclusiv @JellyfinServer1)
  📝 Acțiunea este logată
  ✅ Cont Jellyfin rămâne activ pe server
```

## ⚙️ Instalare

1. Copiază directorul `jellyfinmanager` în directorul de cog-uri al botului Red
2. Încarcă cog-ul:
   ```
   [p]load jellyfinmanager
   ```

## 🚀 Configurare Inițială

```bash
# 1. Adaugă server Jellyfin
[p]server addserver server1 http://jellyfin.example.com admin password123 @JellyfinUsers

# 2. Activează comenzile pe server Discord
[p]server enable

# 3. Setează canal pentru notificări
[p]server setchannel #jellyfin-logs

# 4. Verifică configurația
[p]server listservers
```

## 🎯 Caracteristici Principale

✅ **Simplitate**: Doar două reguli - 7 zile și 90 zile
✅ **Automat**: Nicio intervenție manuală necesară
✅ **Transparent**: Notificări clare pentru toți
✅ **Sigur**: Logging complet pentru audit
✅ **Eficient**: Curățare automată a conturilor neutilizate
✅ **Flexibil**: Utilizatorii pot crea conturi noi oricând

## 🛡️ Siguranță și Privacy

- ✅ Utilizatorii sunt notificați înainte de ștergere
- ✅ Toate acțiunile sunt logate
- ✅ Rolurile sunt eliminate automat la părăsirea serverului
- ✅ Doar owner-ul botului poate reseta utilizatorii
- ✅ Tracking-ul este separat de serverele Jellyfin

## 📝 Note Importante

1. **Conturile Jellyfin** sunt șterse efectiv de pe server
2. **Tracking-ul local** este actualizat în baza de date
3. **Rolurile Discord** sunt eliminate automat când utilizatorul nu mai are conturi active pe acel server Jellyfin
4. **Verificarea** rulează automat la fiecare 24 de ore
5. **Notificările** sunt trimise în DM și în canalul configurat
6. **Permisiuni necesare**: Botul trebuie să aibă permisiunea "Manage Roles" și rolul său trebuie să fie mai sus în ierarhie decât rolurile Jellyfin

## 🐛 Troubleshooting

### Utilizatorii nu sunt șterși
- Verifică că cleanup-ul este activat: `.server listservers`
- Verifică logs pentru erori: verifică console-ul botului
- Testează manual: `.server checkcleanup`

### Notificările nu ajung
- Verifică canalul: `.server setchannel #canal`
- Verifică permisiunile botului în canal
- Verifică că utilizatorii au DM-urile deschise

### Rolurile nu sunt eliminate când ar trebui
- Verifică logs: "Verificare roluri pentru user..."
- Verifică că botul are permisiunea "Manage Roles"
- Verifică că rolul botului este mai sus decât rolurile Jellyfin
- Testează manual cu `.server checkcleanup`

### Rolurile sunt eliminate când nu ar trebui
- Verifică că utilizatorul mai are conturi active: `.utilizator @user`
- Verifică logs pentru detalii despre ștergeri
- Un utilizator trebuie să aibă cel puțin 1 cont ACTIV pentru a păstra rolul

## 📈 Statistici și Monitoring

Plugin-ul loghează:
- ✅ Fiecare verificare zilnică
- ✅ Fiecare utilizator verificat
- ✅ Fiecare ștergere executată
- ✅ Fiecare notificare trimisă
- ✅ Fiecare membru care părăsește serverul

## 🔄 Actualizare de la Versiuni Anterioare

Dacă upgradeezi de la o versiune cu dezactivare:
1. Utilizatorii cu status "disabled" vor rămâne în tracking
2. Nu vor mai fi dezactivați noi utilizatori
3. Utilizatorii "disabled" existenți pot fi șterși manual sau vor fi șterși când ating 90 de zile de la ultima activitate

## 📞 Support

Pentru probleme sau sugestii:
- Verifică logs pentru detalii despre erori
- Testează cu `.server checkcleanup`
- Verifică configurația cu `.server listservers`

## 🎉 Caracteristici Finale

- **Simplu**: Două reguli clare, fără complexitate
- **Automat**: Zero intervenție manuală
- **Transparent**: Toată lumea știe ce se întâmplă
- **Eficient**: Curățare automată, fără resurse irosite
- **Flexibil**: Utilizatorii pot crea conturi noi oricând au nevoie
