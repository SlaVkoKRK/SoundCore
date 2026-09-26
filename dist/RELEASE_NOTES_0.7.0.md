# SoundCore 0.7.0

## Naprawione: nagrania profilu
- Biblioteka `Nagrania profilu` nie zaleĹĽy juĹĽ od spĂłĹşnionego listenera `pywebviewready`.
- `wireRecordingLibrary()` jest uruchamiane z gĹ‚Ăłwnego startu aplikacji po zaĹ‚adowaniu profili.
- WejĹ›cie do `Profile gĹ‚osu` wykonuje jawne `syncRecordingProfileOptions()` + `loadRecordings()`.
- Zmiana/dodanie/usuniÄ™cie prĂłbki odĹ›wieĹĽa bibliotekÄ™ i licznik datasetu.

## Nowe: Song Studio
Nowa zakĹ‚adka `Muzyka / Piosenki` z lokalnymi projektami utworĂłw.

### Projekty
- zapis projektu do `songs/projects/<id>/project.json`,
- tytuĹ‚, jÄ™zyk, dĹ‚ugoĹ›Ä‡, BPM, tonacja, metrum,
- prompt stylu/produkcji,
- tekst z sekcjami `[Intro]`, `[Verse]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Outro]`,
- akordy/harmonia,
- tryb instrumentalny,
- Low-VRAM/chunked,
- profil gĹ‚osu jako metadana projektu,
- historia renderĂłw per projekt.

### Timeline wokalu
- automatyczne tworzenie LRC z tekstu i struktury piosenki,
- podglÄ…d timestampĂłw przed renderem,
- sekcje dajÄ… dodatkowe przerwy aranĹĽacyjne.

### Zaawansowane referencje i edycja
- audio referencyjne stylu zamiast promptu tekstowego,
- tryb `Edit/Regenerate`,
- wskazanie istniejÄ…cego utworu do edycji,
- segmenty czasu np. `[[20,40],[70,90]]`, przekazywane do oficjalnego trybu `--edit` DiffRhythm.

### Lokalny silnik DiffRhythm
- izolowane Ĺ›rodowisko w `engine_runtime/music/diffrhythm`,
- instalacja z GUI,
- modele pobierane przez DiffRhythm przy pierwszym renderze,
- log silnika na ĹĽywo,
- anulowanie generacji,
- render w tle,
- biblioteka WAV z odsĹ‚uchem i eksportem.

### Wymagania DiffRhythm
- Windows wymaga eSpeak NG; SoundCore wykrywa jego instalacjÄ™ i pokazuje czy jest dostÄ™pny,
- RTX 4050 Laptop traktujemy jako konfiguracjÄ™ eksperymentalnÄ… Low-VRAM; `chunked` jest domyĹ›lnie wĹ‚Ä…czony,
- peĹ‚ne modele muzyczne sÄ… duĹĽe i pierwszy render moĹĽe dĹ‚ugo pobieraÄ‡ dane.

## Aktualizator
- `songs/` jest chronione tak samo jak `voice_profiles`, `output` i `engine_runtime`, wiÄ™c projekty i rendery nie sÄ… kasowane podczas aktualizacji SoundCore.
