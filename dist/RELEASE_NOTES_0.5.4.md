# SoundCore 0.5.4

- przebudowane Studio Syntezy: model aktywny/bazowy/wytrenowany, styl, tempo, RVC i zapis WAV,
- test A/B generuje ten sam tekst bazowym i wytrenowanym XTTS bez zmiany aktywnego modelu profilu,
- dodana trwaĹ‚a Historia syntezy z odsĹ‚uchem, eksportem i usuwaniem plikĂłw,
- Pulpit i Studio korzystajÄ… z tego samego backendu; styl na Pulpicie nie jest juĹĽ atrapÄ…,
- wytrenowany XTTS uĹĽywa dzielenia tekstu na zdania podczas inference, co ogranicza ucinanie dĹ‚uĹĽszych wypowiedzi,
- nagrywanie ma inteligentny ogon: po czasie docelowym czeka na krĂłtkÄ… ciszÄ™ zamiast ucinaÄ‡ koĹ„cĂłwkÄ™ sĹ‚owa,
- preprocessing zostawia wiÄ™kszy margines poczÄ…tku/koĹ„ca nagrania,
- wygenerowany WAV dostaje krĂłtki naturalny ogon ciszy.

# SoundCore 0.5.3

- Naprawiono Ĺ‚adowanie fine-tunowanego XTTS w Coqui TTS 0.22.0: `load_checkpoint()` dostaje teraz rĂłwnieĹĽ `checkpoint_dir`, co omija bĹ‚Ä…d `os.path.join(None, "speakers_xtts.pth")`.
- Zachowano wszystkie poprawki 0.5.2 dotyczÄ…ce aktywnego modelu, updatera i obsĹ‚ugi `Esc`.

# SoundCore 0.5.2

- Naprawiono Ĺ‚adowanie aktywnego fine-tunowanego XTTS: przed `Xtts.init_from_config()` SoundCore odnajduje lokalny katalog `XTTS_v2_original_model_files` i uzupeĹ‚nia brakujÄ…ce/stare Ĺ›cieĹĽki `dvae.pth`, `mel_stats.pth`, `vocab.json` i `model.pth`.
- Synteza nie ufa juĹĽ starym absolutnym Ĺ›cieĹĽkom z `metadata.json`; aktywny checkpoint/config/vocab sÄ… ponownie rozwiÄ…zywane z dysku dla profilu.
- BĹ‚Ä…d Ĺ‚adowania wytrenowanego XTTS pokazuje teraz etap i typ wyjÄ…tku zamiast samego `NoneType`.
- Aktualizacja dziaĹ‚a w nieblokujÄ…cej, pĹ‚ywajÄ…cej karcie; reszta aplikacji pozostaje klikalna.
- Dodano realne anulowanie pobierania aktualizacji (`Przerwij` / `Esc`) oraz moĹĽliwoĹ›Ä‡ schowania karty przyciskiem `Ă—` bez przerywania aktualizacji.
- Pasek aktualizacji raportuje rzeczywisty postÄ™p pobierania w MB, gdy GitHub podaje rozmiar paczki.
- `Esc` zamyka/przerywa aktywne elementy UI: nagrywanie, edytor mediĂłw, aktualizacjÄ™, menu/panele i kreator profilu.
- Nagrywanie moĹĽna przerwaÄ‡ w odliczaniu albo w trakcie mikrofonu; backend zatrzymuje `sounddevice` i nie zapisuje anulowanej prĂłbki.

# SoundCore 0.5.1

- Naprawiono bĹ‚Ä…d finalizacji treningu `expected str, bytes or os.PathLike object, not NoneType`.
- `trainer.output_path=None` nie powoduje juĹĽ `Path(None)` po zakoĹ„czeniu treningu.
- Dodano bezpieczny fallback do katalogu profilu oraz rekursywne wyszukiwanie `best_model.pth`, `checkpoint_*.pth` i `config.json`.
- Udany trening nie jest oznaczany jako bĹ‚Ä…d tylko dlatego, ĹĽe Coqui nie zwrĂłciĹ‚o Ĺ›cieĹĽki `output_path`.

# SoundCore 0.5.0

## Aktualizacje
- Sprawdzanie wersji korzysta przede wszystkim z GitHub REST API; raw.githubusercontent.com pozostaje fallbackiem.
- Aktualizacja pobiera i weryfikuje paczkÄ™ w tle, a WebUI pokazuje modal z animowanym spinnerem, etapem i postÄ™pem.
- Restart nastÄ™puje dopiero po przygotowaniu paczki.
- `pip install -r requirements.txt` przy aktualizacji jest uruchamiany tylko wtedy, gdy requirements faktycznie siÄ™ zmieniĹ‚y.

## CiÄ…gĹ‚e nagrywanie datasetu
- Nowy tryb `Sesja ciÄ…gĹ‚a`: Start -> odliczanie -> nagranie -> zapis -> kolejny tekst.
- Sesja trwa do STOP albo wykorzystania wszystkich Ĺ›wieĹĽych tekstĂłw z banku dla danego profilu.
- Widoczny licznik nagranych prĂłbek i czas sesji.
- Tekst pozostaje widoczny w overlayu nagrywania.

## Trening XTTS
- Realna telemetria GPTTrainer: epoka, krok, loss, learning rate i procent postÄ™pu.
- Wykres loss jest rysowany z prawdziwej historii callbackĂłw Trainer.
- Log treningu w GUI Ĺ‚Ä…czy zdarzenia SoundCore i techniczny stdout/stderr Coqui.
- PeĹ‚ny log jest zapisywany jako `voice_profiles/<profil>/training.log`.
- Widoczny czas od ostatniej aktywnoĹ›ci i ostrzeĹĽenie, gdy proces dĹ‚ugo nie raportuje postÄ™pu.
- Trening startuje od normalnej epoki treningowej (`start_with_eval=False`).

## Wytrenowany model profilu
- SoundCore wykrywa `best_model.pth`/checkpoint, `config.json` i `vocab.json` po fine-tuningu.
- W panelu treningu moĹĽna przeĹ‚Ä…czyÄ‡ profil miÄ™dzy `Bazowy XTTS v2` i `Wytrenowany XTTS`.
- WybĂłr jest zapisywany per profil w `metadata.json`.
- Synteza uĹĽywa aktywnego checkpointu profilu i potrafi wrĂłciÄ‡ do bazowego XTTS.
