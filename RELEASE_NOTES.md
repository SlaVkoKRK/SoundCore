# SoundCore 0.6.0

## Voice Engine Lab

- Nowa warstwa wielu silników głosu w Studio Syntezy.
- XTTS v2 pozostaje stabilnym, domyślnym silnikiem dla języka polskiego.
- F5-TTS v1 można zainstalować z GUI do izolowanego `engine_runtime/f5`; inference działa jako osobny proces i nie modyfikuje głównego venv SoundCore.
- Qwen3-TTS 0.6B Base można zainstalować z GUI do izolowanego `engine_runtime/qwen`; SoundCore wymaga osobnego Python 3.12 i używa trybu voice-clone x-vector/Auto jako eksperymentu.
- CosyVoice 3 jest widoczny w laboratorium jako wariant eksperymentalny/manualny; oficjalny stack nie deklaruje języka polskiego.
- Aktualizator chroni `engine_runtime`, więc pobrane środowiska/model cache nie są usuwane przy aktualizacji SoundCore.
- Studio ma wybór silnika oraz A/B pomiędzy: XTTS bazowy, XTTS wytrenowany, F5-TTS i Qwen3-TTS.
- Historia syntezy zapisuje nazwę użytego silnika.

## RVC Manager

- Nowy panel RVC w `Profile głosu`.
- Instalacja `rvc-python` bez ręcznego terminala.
- Wybór modelu `.pth` i opcjonalnego pliku `.index` z GUI.
- Status runtime/modelu per profil oraz możliwość odpięcia RVC.
- Po podpięciu modelu checkbox `Popraw barwę przez RVC` działa jako post-processing wyniku dowolnego dostępnego silnika TTS.

## Stabilność

- Eksperymentalne silniki są izolowane od środowiska XTTS.
- Zachowano wszystkie poprawki 0.5.5 dotyczące bezpiecznego, pojedynczego odtwarzacza A/B.

# SoundCore 0.5.5

## Stabilne odtwarzanie A/B

- Jeden zarządzany odtwarzacz audio dla całej aplikacji.
- Nowy odsłuch A/B, historii, profilu lub ostatniej syntezy bezpiecznie zatrzymuje poprzedni.
- Usunięto równoległe `sd.play()/sd.wait()` z wielu wątków, które mogły crashować PortAudio/aplikację.
- Przełączanie A ↔ B jest responsywne i nie tworzy nakładających się strumieni.
- Błędy urządzenia audio podczas samego odsłuchu nie wywracają procesu GUI.

# SoundCore 0.5.4

- przebudowane Studio Syntezy: model aktywny/bazowy/wytrenowany, styl, tempo, RVC i zapis WAV,
- test A/B generuje ten sam tekst bazowym i wytrenowanym XTTS bez zmiany aktywnego modelu profilu,
- dodana trwała Historia syntezy z odsłuchem, eksportem i usuwaniem plików,
- Pulpit i Studio korzystają z tego samego backendu; styl na Pulpicie nie jest już atrapą,
- wytrenowany XTTS używa dzielenia tekstu na zdania podczas inference, co ogranicza ucinanie dłuższych wypowiedzi,
- nagrywanie ma inteligentny ogon: po czasie docelowym czeka na krótką ciszę zamiast ucinać końcówkę słowa,
- preprocessing zostawia większy margines początku/końca nagrania,
- wygenerowany WAV dostaje krótki naturalny ogon ciszy.

# SoundCore 0.5.3

- Naprawiono ładowanie fine-tunowanego XTTS w Coqui TTS 0.22.0: `load_checkpoint()` dostaje teraz również `checkpoint_dir`, co omija błąd `os.path.join(None, "speakers_xtts.pth")`.
- Zachowano wszystkie poprawki 0.5.2 dotyczące aktywnego modelu, updatera i obsługi `Esc`.

# SoundCore 0.5.2

- Naprawiono ładowanie aktywnego fine-tunowanego XTTS: przed `Xtts.init_from_config()` SoundCore odnajduje lokalny katalog `XTTS_v2_original_model_files` i uzupełnia brakujące/stare ścieżki `dvae.pth`, `mel_stats.pth`, `vocab.json` i `model.pth`.
- Synteza nie ufa już starym absolutnym ścieżkom z `metadata.json`; aktywny checkpoint/config/vocab są ponownie rozwiązywane z dysku dla profilu.
- Błąd ładowania wytrenowanego XTTS pokazuje teraz etap i typ wyjątku zamiast samego `NoneType`.
- Aktualizacja działa w nieblokującej, pływającej karcie; reszta aplikacji pozostaje klikalna.
- Dodano realne anulowanie pobierania aktualizacji (`Przerwij` / `Esc`) oraz możliwość schowania karty przyciskiem `×` bez przerywania aktualizacji.
- Pasek aktualizacji raportuje rzeczywisty postęp pobierania w MB, gdy GitHub podaje rozmiar paczki.
- `Esc` zamyka/przerywa aktywne elementy UI: nagrywanie, edytor mediów, aktualizację, menu/panele i kreator profilu.
- Nagrywanie można przerwać w odliczaniu albo w trakcie mikrofonu; backend zatrzymuje `sounddevice` i nie zapisuje anulowanej próbki.

# SoundCore 0.5.1

- Naprawiono błąd finalizacji treningu `expected str, bytes or os.PathLike object, not NoneType`.
- `trainer.output_path=None` nie powoduje już `Path(None)` po zakończeniu treningu.
- Dodano bezpieczny fallback do katalogu profilu oraz rekursywne wyszukiwanie `best_model.pth`, `checkpoint_*.pth` i `config.json`.
- Udany trening nie jest oznaczany jako błąd tylko dlatego, że Coqui nie zwróciło ścieżki `output_path`.

# SoundCore 0.5.0

## Aktualizacje
- Sprawdzanie wersji korzysta przede wszystkim z GitHub REST API; raw.githubusercontent.com pozostaje fallbackiem.
- Aktualizacja pobiera i weryfikuje paczkę w tle, a WebUI pokazuje modal z animowanym spinnerem, etapem i postępem.
- Restart następuje dopiero po przygotowaniu paczki.
- `pip install -r requirements.txt` przy aktualizacji jest uruchamiany tylko wtedy, gdy requirements faktycznie się zmieniły.

## Ciągłe nagrywanie datasetu
- Nowy tryb `Sesja ciągła`: Start -> odliczanie -> nagranie -> zapis -> kolejny tekst.
- Sesja trwa do STOP albo wykorzystania wszystkich świeżych tekstów z banku dla danego profilu.
- Widoczny licznik nagranych próbek i czas sesji.
- Tekst pozostaje widoczny w overlayu nagrywania.

## Trening XTTS
- Realna telemetria GPTTrainer: epoka, krok, loss, learning rate i procent postępu.
- Wykres loss jest rysowany z prawdziwej historii callbacków Trainer.
- Log treningu w GUI łączy zdarzenia SoundCore i techniczny stdout/stderr Coqui.
- Pełny log jest zapisywany jako `voice_profiles/<profil>/training.log`.
- Widoczny czas od ostatniej aktywności i ostrzeżenie, gdy proces długo nie raportuje postępu.
- Trening startuje od normalnej epoki treningowej (`start_with_eval=False`).

## Wytrenowany model profilu
- SoundCore wykrywa `best_model.pth`/checkpoint, `config.json` i `vocab.json` po fine-tuningu.
- W panelu treningu można przełączyć profil między `Bazowy XTTS v2` i `Wytrenowany XTTS`.
- Wybór jest zapisywany per profil w `metadata.json`.
- Synteza używa aktywnego checkpointu profilu i potrafi wrócić do bazowego XTTS.
