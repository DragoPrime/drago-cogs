# Jarvix — comenzi în limba naturală pentru Red Discord Bot 3.5

Scrii o cerere obișnuită, începând cu mențiunea botului, iar un AI local (Ollama) alege
singur, dintre comenzile **deja încărcate** în Red (din orice cog), comanda potrivită.

```
@Bot schimbă numele canalului #canal1 în canal2
```

Botul răspunde cu ce a înțeles și ce va rula, de exemplu:

> Redenumesc canalul. Vrei să rulez: `!editchannel name #canal1 canal2` ?  **[Execută] [Anulează]**

Nu trebuie să-i explici nimic: catalogul de comenzi (nume, parametri, text de ajutor) se
citește automat din Red și rămâne la zi când încarci/descarci cog-uri.

## Cerințe

- Red Discord Bot 3.5+
- Ollama pornit, cu un model care știe JSON structurat (ex: `qwen3:8b`)
- Intent-ul **Message Content** activat pentru bot (ca pentru orice bot cu comenzi cu prefix)

## Instalare

```
[p]addpath /calea/care/contine/folderul/jarvix
[p]load jarvix
[p]jarvix url http://localhost:11434
[p]jarvix model qwen3:8b
```

(`url`, `model`, `gandire`, `timeout` și `blocate` sunt rezervate **proprietarului botului**.)

## Cum funcționează (pe scurt)

1. **Cuvinte-cheie:** modelul transformă cererea (în română) în cuvinte-cheie în engleză,
   pentru că numele comenzilor sunt în engleză.
2. **Scurtlistă:** Jarvix scorează toate comenzile și păstrează cele mai probabile (implicit 15),
   **doar dintre cele pe care tu ai voie să le rulezi** (verificat cu sistemul de permisiuni Red).
3. **Alegerea:** modelul alege o comandă *din scurtlistă* și scrie argumentele.
4. **Validare:** Jarvix cere Red să interpreteze comanda finală. Dacă numele nu e în listă, dacă
   argumentele ar duce la altă comandă/subcomandă, sau dacă e blocată → nu se execută nimic.
5. **Confirmare** (implicit activată): vezi exact comanda și apeși **Execută** sau **Anulează**.
   Doar cel care a făcut cererea poate apăsa.
6. **Execuție:** comanda rulează **în numele tău**, prin sistemul normal de comenzi Red, deci cu
   exact aceleași verificări (permisiuni Discord, `[p]permissions`, comenzi doar pentru owner etc.).
   Cine nu poate rula o comandă manual nu o poate rula nici prin Jarvix. Mesajul primește ✅ sau ❌.

## Siguranță

- **Lista de comenzi blocate:** implicit sunt interzise `eval`, `debug`, `repl`, `load`, `unload`,
  `reload`, `shutdown`, `restart`, `leave`, `set token`, `set api`, `set owner`, `repo`, `cog`,
  `bankset reset` ș.a. (cu tot cu subcomenzi). Owner-ul o poate modifica:
  ```
  [p]jarvix blocate                    (listează)
  [p]jarvix blocate adauga ban         (blochează și `ban`)
  [p]jarvix blocate sterge ban
  [p]jarvix blocate reseteaza
  ```
- Jarvix **nu își poate rula propriile comenzi** (AI-ul nu își poate schimba setările).
- **Nu opri confirmarea** decât dacă ai încredere în model: un model de 8B mai greșește uneori
  comanda sau argumentele. Cu confirmarea activă vezi exact ce se va rula.
- Textul cererii se trimite doar către serverul Ollama configurat. Jarvix nu salvează mesaje.
- Cererile au cooldown per utilizator (implicit 10 secunde) și Jarvix poate fi limitat la anumite canale.

## Comenzi de configurare (`[p]jarvix ...`)

| Comandă | Descriere |
|---|---|
| `test <cerere>` | **Simulează** o cerere fără a executa nimic: arată cuvintele-cheie, candidații, alegerea modelului și comanda finală |
| `comenzi [text]` | Câte comenzi vede Jarvix; opțional, caută după nume |
| `setari` | Afișează configurația |
| `toggle` | Activează/dezactivează Jarvix pe server |
| `confirmare` | Activează/dezactivează confirmarea cu butoane |
| `cooldown <s>` | Timp minim între cererile aceluiași utilizator |
| `candidati <5-30>` | Câte comenzi candidate primește modelul |
| `canale [adauga/sterge/toate] [#canal]` | Limitează Jarvix la anumite canale |
| `logcanal [#canal]` | Canal unde se notează ce comenzi au fost rulate |
| `url`, `model`, `gandire`, `timeout` | (Owner) Setări Ollama |
| `blocate [adauga/sterge/reseteaza]` | (Owner) Comenzi interzise AI-ului |

Dacă un rezultat nu e cel așteptat, rulează mai întâi
`[p]jarvix test schimbă numele canalului #canal1 în canal2` și vezi la ce pas se oprește.

## Limitări

- Funcționează doar cu comenzile care există. Pentru „schimbă numele canalului” trebuie să existe
  în Red o comandă care face asta (de ex. din cog-ul Admin sau unul instalat de tine).
- Comenzile care cer răspunsuri ulterioare/meniuri interactive nu se potrivesc bine.
- Calitatea alegerii depinde de textul de ajutor al comenzilor: cog-uri fără descrieri sunt găsite mai greu.
- Mesajul trebuie să **înceapă** cu mențiunea botului. Dacă începe cu o comandă reală
  (`@Bot help`), Red o rulează normal, fără Jarvix.
