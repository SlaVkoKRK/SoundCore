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
