# SoundCore 0.7.1

Hotfix uruchamiania na Pythonie 3.10.

- naprawiono SyntaxError w `music/song_manager.py` powodujący brak startu SoundCore 0.7.0,
- usunięto regex z wyrażenia wewnątrz f-stringa; nazwa renderu piosenki jest teraz wyliczana wcześniej,
- zachowano wszystkie funkcje 0.7.0 bez zmian.

# SoundCore 0.7.0

## Naprawione: nagrania profilu
- Biblioteka `Nagrania profilu` nie zależy już od spóźnionego listenera `pywebviewready`.
- `wireRecordingLibrary()` jest uruchamiane z głównego startu aplikacji po załadowaniu profili.
- Wejście do `Profile głosu` wykonuje jawne `syncRecordingProfileOptions()` + `loadRecordings()`.
- Zmiana/dodanie/usunięcie próbki odświeża bibliotekę i licznik datasetu.

## Nowe: Song Studio
Nowa zakładka `Muzyka / Piosenki` z lokalnymi projektami utworów.

### Projekty
- zapis projektu do `songs/projects/<id>/project.json`,
- tytuł, język, długość, BPM, tonacja, metrum,
- prompt stylu/produkcji,
- tekst z sekcjami `[Intro]`, `[Verse]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Outro]`,
- akordy/harmonia,
- tryb instrumentalny,
- Low-VRAM/chunked,
- profil głosu jako metadana projektu,
- historia renderów per projekt.

### Timeline wokalu
- automatyczne tworzenie LRC z tekstu i struktury piosenki,
- podgląd timestampów przed renderem,
- sekcje dają dodatkowe przerwy aranżacyjne.

### Zaawansowane referencje i edycja
- audio referencyjne stylu zamiast promptu tekstowego,
- tryb `Edit/Regenerate`,
- wskazanie istniejącego utworu do edycji,
- segmenty czasu np. `[[20,40],[70,90]]`, przekazywane do oficjalnego trybu `--edit` DiffRhythm.

### Lokalny silnik DiffRhythm
- izolowane środowisko w `engine_runtime/music/diffrhythm`,
- instalacja z GUI,
- modele pobierane przez DiffRhythm przy pierwszym renderze,
- log silnika na żywo,
- anulowanie generacji,
- render w tle,
- biblioteka WAV z odsłuchem i eksportem.

### Wymagania DiffRhythm
- Windows wymaga eSpeak NG; SoundCore wykrywa jego instalację i pokazuje czy jest dostępny,
- RTX 4050 Laptop traktujemy jako konfigurację eksperymentalną Low-VRAM; `chunked` jest domyślnie włączony,
- pełne modele muzyczne są duże i pierwszy render może długo pobierać dane.

## Aktualizator
- `songs/` jest chronione tak samo jak `voice_profiles`, `output` i `engine_runtime`, więc projekty i rendery nie są kasowane podczas aktualizacji SoundCore.
