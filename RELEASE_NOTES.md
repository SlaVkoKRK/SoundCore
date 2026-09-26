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
