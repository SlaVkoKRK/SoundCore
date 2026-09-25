# SoundCore

SoundCore to lokalna aplikacja desktopowa do nagrywania głosu, klonowania mowy przez XTTS-v2 oraz trenowania własnego modelu głosu metodą fine-tuningu GPT encodera XTTS-v2.

## Najważniejsze funkcje

- nagrywanie i czyszczenie próbek głosu z mikrofonu,
- profile głosowe przechowywane lokalnie,
- XTTS-v2 zero-shot voice cloning,
- własny dataset: nagrywanie zdań wraz z dokładną transkrypcją,
- fine-tuning XTTS-v2 przez `GPTTrainer`,
- trening na NVIDIA CUDA lub CPU,
- osobny proces treningowy, dzięki czemu GUI nie jest blokowane,
- automatyczne używanie wytrenowanego modelu podczas syntezy,
- opcjonalny post-processing RVC,
- aktualizacje z GitHub Releases z weryfikacją SHA256,
- publiczna dystrybucja źródeł bez lokalnych profili, nagrań i modeli.

## Wymagania

Zalecany jest Python 3.10. Stos Coqui TTS/XTTS jest wrażliwy na wersje PyTorch, Transformers i NumPy, dlatego korzystaj z wersji zapisanych w `requirements.txt`.

```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

### NVIDIA CUDA

SoundCore wykrywa CUDA przez PyTorch. Jeżeli chcesz trenować na GPU, zainstaluj build PyTorch zgodny z CUDA dla swojej karty, a następnie pozostałe zależności. W zakładce **Trening modelu** pojawi się `GPU / CUDA — <nazwa karty>`.

CPU jest obsługiwane funkcjonalnie, jednak fine-tuning XTTS-v2 może być na nim wielokrotnie wolniejszy.

## Trening własnego głosu

1. Utwórz profil w zakładce **Nagrywanie**.
2. Otwórz **Trening modelu** i wybierz profil.
3. Nagrywaj wyświetlane zdania. Każda próbka trafia do prywatnego katalogu profilu `voice_profiles/<profil>/dataset/`.
4. Zalecane jest co najmniej kilkadziesiąt czystych, zróżnicowanych próbek. GUI pozwala uruchomić trening od 5 próbek wyłącznie po to, by dało się sprawdzić pipeline.
5. Wybierz `GPU / CUDA` albo `CPU`, liczbę epok i kliknij **Rozpocznij GPTTrainer**.
6. Checkpoint, konfiguracja i wynik treningu są przechowywane w `voice_profiles/<profil>/model/`.
7. W **Syntezie mowy** pozostaw zaznaczone **Użyj wytrenowanego modelu XTTS**. Jeśli profil ma prawidłowy checkpoint, SoundCore użyje go zamiast zwykłego zero-shot.

SoundCore opiera trening na oficjalnej architekturze Coqui XTTS-v2: `GPTArgs`, `GPTTrainerConfig`, `GPTTrainer` i `Trainer`.

## Dane prywatne

Repozytorium nie powinno zawierać danych użytkownika. `.gitignore` blokuje m.in.:

- `voice_profiles/`,
- pliki WAV w `output/`,
- `*.pth`, `*.pt`, `*.ckpt`, `*.index`,
- `.env`, klucze i tokeny,
- cache i środowiska wirtualne.

Przed publikacją zawsze warto dodatkowo wykonać `git status` i sprawdzić listę plików.

## Aktualizacje

Zakładka **Aktualizacje** pobiera:

`https://raw.githubusercontent.com/SlaVkoKRK/SoundCore/main/dist/channel.json`

Kanał wskazuje wersję, URL paczki i SHA256. SoundCore:

1. sprawdza numer wersji,
2. pobiera paczkę z GitHub Release,
3. weryfikuje SHA256,
4. sprawdza ścieżki archiwum przed rozpakowaniem,
5. zamyka aplikację,
6. podmienia kod,
7. zachowuje `voice_profiles`, `output`, `venv/.venv` i `.git`,
8. uruchamia SoundCore ponownie.

## Publikacja na GitHub

W katalogu projektu znajduje się `publish_soundcore.ps1`. Jest wzorowany na publisherze VEYRA i używa GitHub CLI (`gh`). Domyślne repozytorium to:

`SlaVkoKRK/SoundCore`

Jeśli repo jeszcze nie istnieje, skrypt utworzy je jako **publiczne**. Następnie publikuje źródła, tworzy GitHub Release i dopiero na końcu aktywuje nowy `dist/channel.json`.

```powershell
.\publish_soundcore.ps1
```

Można wskazać inne repo:

```powershell
.\publish_soundcore.ps1 -Repo "TwojLogin/SoundCore"
```

Wymagane:

```powershell
winget install --id GitHub.cli
gh auth login
```

Skrypt buduje:

- `soundcore_update.tar.gz` — paczka dla automatycznego aktualizatora,
- `SoundCore-<wersja>-source.tar.gz` — pełne publiczne źródła,
- pliki SHA256,
- `release.json`,
- informacje o wydaniu,
- `channel.json`.

## Struktura

```text
soundcore/
├── main.py
├── version.py
├── gui/
├── recorder/
├── preprocessing/
├── storage/
├── voice_engine/
├── training/
│   ├── dataset.py
│   ├── manager.py
│   └── train_xtts.py
├── updater/
│   ├── update_manager.py
│   └── apply_update.py
├── tools/
│   └── build_release.py
├── voice_profiles/       # prywatne, niepublikowane
├── output/               # prywatne, niepublikowane
└── publish_soundcore.ps1
```

## Wersja

Aktualna wersja: **0.2.0**.
