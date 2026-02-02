# JellyfinSearch - Plugin Multi-Server pentru Red Discord Bot

## Modificări față de versiunea originală

### Principalele schimbări:

1. **Suport pentru multiple servere Jellyfin**
   - Poți adăuga oricâte servere dorești
   - Fiecare server are un nume personalizat
   - Căutarea se face simultan pe toate serverele configurate

2. **Comandă nouă: `!cauta`**
   - Comanda `!freia` a fost înlocuită cu `!cauta`
   - Mai generică și nu mai este specifică unui singur server

3. **Sistem nou de configurare**
   - Comenzile de configurare sunt acum grupate sub `!jellyfinset`
   - Gestionare mai ușoară a serverelor multiple

## Comenzi disponibile

### Configurare (doar pentru owner)

#### Adăugare server nou
```
!jellyfinset addserver <nume_server> <url> <api_key>
```
**Exemplu:**
```
!jellyfinset addserver Freia https://jellyfin.example.com abc123def456
!jellyfinset addserver Server2 https://jellyfin2.example.com xyz789uvw012
```

#### Eliminare server
```
!jellyfinset removeserver <nume_server>
```
**Exemplu:**
```
!jellyfinset removeserver Freia
```

#### Listare servere configurate
```
!jellyfinset listservers
```
Afișează toate serverele configurate cu URL-urile lor.

#### Setare cheie API TMDB
```
!jellyfinset tmdb <api_key>
```
**Exemplu:**
```
!jellyfinset tmdb your_tmdb_api_key_here
```

### Căutare (pentru toți utilizatorii)

```
!cauta <titlu_film_sau_serial>
```
**Exemple:**
```
!cauta Inception
!cauta Breaking Bad
!cauta The Matrix
```

## Cum funcționează căutarea

1. **Căutare TMDB** (dacă este configurată)
   - Se caută pe TMDB pentru a găsi toate variantele de titluri
   - Titluri în limba originală
   - Titluri traduse
   - Titluri alternative

2. **Căutare pe toate serverele**
   - Fiecare server este căutat cu toate variantele de titluri
   - Rezultatele sunt combinate și deduplicate

3. **Îmbogățire cu informații TMDB**
   - Primele 10 rezultate primesc informații suplimentare de la TMDB
   - Postere de calitate
   - Descrieri detaliate
   - Evaluări

4. **Afișare rezultate**
   - Navigare cu butoane ⬅️ și ➡️
   - Buton 🔍 pentru link direct
   - Informații despre serverul pe care se află fiecare titlu

## Instalare

1. Copiază fișierul `jellyfin.py` modificat în directorul cog-ului tău:
   ```
   /path/to/redbot/cogs/jellyfinsearch/jellyfin.py
   ```

2. Reîncarcă cog-ul în Discord:
   ```
   !reload jellyfinsearch
   ```

3. Configurează serverele:
   ```
   !jellyfinset addserver Server1 https://jellyfin1.example.com api_key_1
   !jellyfinset addserver Server2 https://jellyfin2.example.com api_key_2
   !jellyfinset tmdb your_tmdb_api_key
   ```

4. Testează căutarea:
   ```
   !cauta Inception
   ```

## Notă despre compatibilitate

Această versiune NU este compatibilă backwards cu versiunea veche. Dacă ai configurat deja serverul cu comenzile vechi (`!setjellyfinurl`, `!setjellyfinapi`), va trebui să reconfirezi serverele folosind noile comenzi:

```
!jellyfinset addserver NumeleTau <url_vechi> <api_key_vechi>
```

## Beneficii

✅ Caută pe multiple servere simultan
✅ Rezultate mai complete
✅ Gestionare mai ușoară a serverelor
✅ Nume de comandă mai generic
✅ Afișează sursa fiecărui rezultat

## Funcționalități păstrate

- Integrare TMDB pentru informații detaliate
- Navigare prin rezultate cu butoane
- Link-uri directe către conținut
- Afișare postere și descrieri
- Support pentru filme și seriale
