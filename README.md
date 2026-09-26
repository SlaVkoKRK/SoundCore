**Current release: 0.7.5**


## Song Studio (0.7.0)
SoundCore zawiera lokalne studio piosenek z projektami, strukturą utworu, tekstem, BPM, tonacją, metrum, harmonią, timeline LRC, referencją audio oraz edycją wybranych fragmentów. Pierwszym zintegrowanym silnikiem jest DiffRhythm, instalowany do odizolowanego `engine_runtime/music/diffrhythm`. Projekty i rendery są zapisywane w `songs/` i chronione przez updater.

> Current release: **0.6.0**

# SoundCore – AI SoundSystem

Aplikacja desktopowa (Python) do klonowania głosu i syntezy mowy (TTS).
Program nagrywa próbkę głosu z mikrofonu (wbudowanego lub USB), na jej
podstawie "uczy się" barwy głosu i sposobu mówienia (dykcji, intonacji),
a następnie potrafi odczytać dowolny tekst w tym głosie.

## SoundCore 0.6 – Voice Engine Lab

SoundCore obsługuje teraz warstwę wielu silników TTS. XTTS v2 pozostaje silnikiem stabilnym i domyślnym dla języka polskiego. F5-TTS oraz Qwen3-TTS mogą być instalowane w osobnych środowiskach pod `engine_runtime/`, dzięki czemu ich zależności nie zmieniają środowiska głównej aplikacji. W Studio można porównywać silniki A/B na tej samej referencji.

RVC ma własny manager w zakładce Profile głosu: instalacja runtime, wybór `.pth`, opcjonalnego `.index` i status profilu. RVC jest post-processingiem — najpierw wybrany silnik TTS generuje mowę, a następnie RVC może zmienić jej barwę.


## Spis treści

1. [Architektura projektu](#architektura-projektu)
2. [Jak to działa – podejście techniczne](#jak-to-działa--podejście-techniczne)
3. [Instalacja](#instalacja)
4. [Uruchomienie](#uruchomienie)
5. [Instrukcja użytkowania](#instrukcja-użytkowania)
6. [Poprawa wierności głosu przez RVC (opcjonalnie)](#poprawa-wierności-głosu-przez-rvc-opcjonalnie)
7. [Ograniczenia i możliwości rozwoju](#ograniczenia-i-możliwości-rozwoju)
8. [Zagadnienia do prezentacji/obrony projektu](#zagadnienia-do-prezentacjiobrony-projektu)

---

## Architektura projektu

```
soundcore/
├── main.py                    # punkt wejścia aplikacji
├── requirements.txt
├── recorder/
│   └── recorder.py            # nagrywanie z mikrofonu, listowanie urządzeń, odtwarzanie
├── preprocessing/
│   └── audio_utils.py         # czyszczenie audio: normalizacja, VAD, resampling
├── voice_engine/
│   ├── tts_engine.py          # wrapper na model Coqui XTTS-v2 (klonowanie głosu + TTS)
│   └── rvc_engine.py          # opcjonalny wrapper na RVC (poprawa barwy głosu)
├── requirements-rvc.txt       # opcjonalne zależności modułu RVC
├── storage/
│   └── profile_manager.py     # zapisywanie/wczytywanie profili głosowych na dysku
├── gui/
│   └── app.py                 # interfejs graficzny (Tkinter)
├── voice_profiles/            # tu zapisywane są profile głosowe użytkowników
└── output/                    # tu zapisywane są wygenerowane pliki mowy
```

Podział na moduły odzwierciedla pipeline przetwarzania danych:

```
Mikrofon → [recorder] → surowe audio
                 ↓
        [preprocessing] → oczyszczona próbka referencyjna
                 ↓
         [storage] → zapisany profil głosowy (wav + metadane)
                 ↓
   tekst + profil → [voice_engine] → wygenerowana mowa (wav)
                 ↓
              odtworzenie
```

## Jak to działa – podejście techniczne

Pełne trenowanie modelu TTS "od zera" na pojedynczym głosie wymagałoby
dziesiątek godzin nagrań i dużej mocy obliczeniowej (dni treningu na GPU),
co jest nierealne w skali projektu studenckiego. Dlatego SoundCore
wykorzystuje podejście **voice cloning (few-shot speaker adaptation)**:

- Gotowy, wytrenowany wcześniej model wielojęzyczny (**Coqui XTTS-v2**)
  potrafi na podstawie krótkiej próbki referencyjnej (kilkanaście-
  kilkadziesiąt sekund nagrania) wyodrębnić tzw. **embedding mówcy**
  (ang. *speaker embedding*) – wektor liczbowy opisujący barwę głosu,
  tempo mówienia i charakterystyczne cechy wymowy.
- Ten embedding jest następnie wykorzystywany w trakcie generowania
  mowy (inferencji), warunkując model tak, by wygenerowany dźwięk
  brzmiał jak głos z próbki – bez potrzeby ponownego trenowania sieci.
- Dzięki temu "nauka" głosu trwa sekundy (samo przetworzenie próbki),
  a nie godziny/dni, jak przy klasycznym treningu modelu TTS od zera.

Model automatycznie wykorzystuje GPU (CUDA), jeśli jest dostępne –
w przeciwnym razie działa na CPU (wolniej, ale w pełni funkcjonalnie).

## Instalacja

Wymagany Python 3.10 lub 3.11 (zalecane ze względu na kompatybilność
biblioteki `TTS`).

```bash
# 1. Utwórz i aktywuj wirtualne środowisko (zalecane)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 2. Zainstaluj zależności
pip install -r requirements.txt
```

Na Linuksie może być potrzebny systemowy pakiet Tkinter:
```bash
sudo apt install python3-tk        # Ubuntu/Debian
sudo dnf install python3-tkinter   # Fedora
```

Jeśli masz kartę graficzną NVIDIA i chcesz przyspieszenia GPU, zainstaluj
najpierw wersję `torch` z obsługą CUDA zgodnie z instrukcją na
[pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/),
a dopiero potem `pip install TTS`. Bez tego kroku aplikacja i tak zadziała –
automatycznie wykryje brak GPU i przełączy się na CPU.

## Uruchomienie

```bash
python main.py
```

Przy **pierwszym** wygenerowaniu mowy aplikacja pobierze model XTTS-v2
(ok. 1.5–2 GB) z repozytorium Coqui – wymagane jest wtedy połączenie
z internetem. Kolejne uruchomienia działają już offline (model jest
zapisany w lokalnym cache).

## Instrukcja użytkowania

1. **Zakładka „Nagrywanie”**
   - Wybierz mikrofon z listy urządzeń.
   - Ustaw długość nagrania (zalecane min. 15–20 sekund).
   - Kliknij „Rozpocznij nagrywanie” i mów naturalnie, wyraźnie.
   - Odsłuchaj nagranie, nadaj mu nazwę i zapisz jako profil głosowy.

2. **Zakładka „Profile głosowe”**
   - Przeglądaj zapisane profile, odsłuchuj próbki referencyjne,
     usuwaj niepotrzebne profile.

3. **Zakładka „Synteza mowy”**
   - Wybierz profil głosowy i język tekstu.
   - Wpisz tekst do wypowiedzenia.
   - Kliknij „Generuj i odtwórz” – wygenerowany plik zostanie zapisany
     w folderze `output/` i automatycznie odtworzony.

## Poprawa wierności głosu przez RVC (opcjonalnie)

Zero-shot cloning w XTTS (opisany wyżej) ma naturalny sufit jakości –
generuje głos "podobny", ale nie identyczny z oryginałem, bo nie jest
trenowany na Twoim głosie, tylko warunkowany krótką próbką. Aby zbliżyć
się bardziej do 1:1, SoundCore obsługuje dodatkowy, opcjonalny krok:
konwersję wygenerowanej mowy przez **RVC (Retrieval-based Voice
Conversion)** – technikę, która wymaga jednorazowego wytrenowania
małego modelu bezpośrednio na Twoim głosie.

### Jak to działa

```
tekst → XTTS (klonowanie zero-shot) → surowe audio
                                            ↓
                          RVC (model wytrenowany na Twoim głosie)
                                            ↓
                              audio z poprawioną barwą głosu
```

RVC nie generuje mowy z tekstu – konwertuje już istniejące audio,
zamieniając barwę głosu na tę, na której model był trenowany. Ponieważ
model jest realnie douczony (a nie tylko "zero-shot"), wierność barwy
jest zwykle zauważalnie lepsza.

### Krok 1: Zainstaluj zależności RVC

```bash
pip install -r requirements-rvc.txt
```

(Ten krok jest opcjonalny – jeśli go pominiesz, reszta aplikacji działa
normalnie, po prostu bez opcji poprawy barwy głosu.)

### Krok 2: Wytrenuj własny model RVC (narzędzie zewnętrzne)

Pisanie własnego pipeline'u treningowego RVC od zera wykracza poza ten
projekt (wymaga m.in. ekstrakcji cech HuBERT, budowy indeksu FAISS,
pętli treningowej – to osobny, duży projekt sam w sobie). Zamiast tego
użyj dojrzałego, gotowego narzędzia, np. **Applio**
(https://github.com/IAHispano/Applio) – forka RVC z prostym
jednoklikowym instalatorem, lub oryginalnego
**RVC-Project WebUI** (https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI).
Sprawdź aktualny stan tych projektów – narzędzia community potrafią się
zmieniać/przenosić.

Ogólny proces (szczegóły w dokumentacji wybranego narzędzia):
1. Nagraj 5–15+ minut czystego, zróżnicowanego audio swojego głosu
   (im więcej i czystsze nagrania, tym lepszy efekt).
2. W narzędziu treningowym uruchom preprocessing (dzielenie na
   fragmenty, ekstrakcja cech) i trening (na CPU realnie liczony w
   dziesiątkach minut do kilku godzin, zależnie od ilości danych i mocy
   procesora; na GPU znacznie szybciej).
3. Po treningu będziesz mieć dwa pliki: `<nazwa>.pth` (model) i
   opcjonalnie `<nazwa>.index` (indeks poprawiający precyzję barwy).

### Krok 3: Podepnij model w SoundCore

1. W zakładce **„Profile głosowe”** wybierz profil z listy i kliknij
   **„🎚 Podepnij model RVC”**.
2. Wskaż plik `.pth`, a następnie (opcjonalnie) plik `.index`.
3. W zakładce **„Synteza mowy”** zaznacz checkbox **„Popraw barwę głosu
   przez RVC”** przed kliknięciem „Generuj i odtwórz”.

Wygenerowana mowa zostanie najpierw stworzona przez XTTS, a następnie
automatycznie przepuszczona przez Twój model RVC.

### Uwaga o konfliktach zależności

Stos zależności RVC (`fairseq`, `faiss`, `torchcrepe`, `pyworld`) bywa
równie wymagający jak TTS/XTTS. Jeśli napotkasz konflikty wersji
(numpy/torch/itp.), stosuj tę samą strategię co przy instalacji TTS:
instaluj pakiety pojedynczo i czytaj dokładnie komunikaty błędów –
zwykle wskazują dokładnie, którą wersję czego przypiąć.

## Ograniczenia i możliwości rozwoju



**Ograniczenia obecnej wersji:**
- Jakość klonowania głosu zależy od czystości próbki referencyjnej
  (zalecane nagrywanie w cichym pomieszczeniu, bez echa i szumów tła).
- Generowanie na CPU jest wolniejsze niż na GPU (dłuższe zdania mogą
  generować się kilkanaście-kilkadziesiąt sekund).
- Model nie jest douczany (fine-tuned) na danych użytkownika trwale –
  klonowanie odbywa się "w locie" (zero-shot/few-shot) przy każdej syntezie.

**Możliwe kierunki rozwoju (dobre pod dalszą część projektu/pracę dyplomową):**
- Fine-tuning modelu na większym zbiorze nagrań danej osoby (trwałe
  dostrojenie wag sieci, a nie tylko embedding mówcy) – wyższa jakość
  kosztem dłuższego treningu.
- Dodanie modułu redukcji szumów (np. RNNoise, DeepFilterNet) przed
  zapisem próbki referencyjnej.
- Kontrola prozodii/emocji w generowanej mowie.
- Wersja webowa (nagrywanie przez przeglądarkę + backend API).
- Eksport/import profili głosowych (współdzielenie między instalacjami).

## Zagadnienia do prezentacji/obrony projektu

Warto umieć krótko wyjaśnić:
- **Speaker embedding** – jak model reprezentuje "tożsamość" głosu jako
  wektor liczbowy, niezależnie od wypowiadanego tekstu.
- **Mel-spektrogram** – pośrednia reprezentacja dźwięku (czasowo-
  częstotliwościowa), na której operują modele TTS przed etapem wokodera.
- **Wokoder (vocoder)** – sieć neuronowa zamieniająca mel-spektrogram
  z powrotem na falę dźwiękową (surowe próbki audio).
- **Zero-/few-shot voice cloning** – różnica między klonowaniem "w locie"
  (bez treningu) a pełnym fine-tuningiem modelu na głosie danej osoby.
- **VAD (Voice Activity Detection)** – wykrywanie fragmentów mowy vs.
  cisza/szum, zastosowane tu do przycinania nagrań.
- Dlaczego pełny trening TTS od zera jest niepraktyczny w tej skali
  (ilość danych, czas treningu, moc obliczeniowa) – i dlaczego transfer
  learning / voice cloning to rozsądny kompromis.

## Dynamiczne teksty nagraniowe

Od wersji 0.3.5 SoundCore korzysta z lokalnej bazy polskich promptów nagraniowych. Backend dobiera i łączy fragmenty do wybranego czasu próbki. Profile referencyjne otrzymują tekst naturalny, a dataset treningowy rotuje materiał fonetyczny, liczby, pytania, prozodię i tekst techniczny. Bazę można rozszerzać w `training/prompts_pl.json`.

### Historia tekstów per profil

Od wersji 0.3.6 SoundCore zapisuje użyte prompty w `voice_profiles/<profil>/prompt_history.json`. Generator preferuje zdania, których dany profil jeszcze nie czytał. Historia jest lokalna, należy do profilu i jest zachowywana przez system aktualizacji razem z `voice_profiles`.

### Wyszukiwanie i menu użytkownika

Globalną wyszukiwarkę otwiera `Ctrl+K`. Wyszukuje moduły SoundCore i profile głosowe. Menu użytkownika w prawym górnym rogu udostępnia ustawienia, katalog SoundCore, restart programu i informacje o wersji.

## Recording library and media import (0.3.8)
Each voice profile now has its own recording library. SoundCore can import audio and video files, extract mono audio with FFmpeg, display a waveform, trim a selected range, preview it, and save only that clip into the profile dataset. Imported samples keep source/trim metadata and their transcript can be edited later.

## Fast Start (0.3.9+)

SoundCore uruchamia WebUI w pierwszej kolejności. Ciężkie biblioteki AI/audio nie blokują już pojawienia się okna:

- GPU/CUDA i mikrofony są wykrywane w tle,
- XTTS jest ładowany dopiero przy pierwszej syntezie,
- RVC dopiero po jego użyciu,
- SciPy/NumPy/sounddevice są importowane dopiero przez funkcje, które ich potrzebują,
- ostatni stan sprzętu jest przechowywany lokalnie w `cache/hardware.json`.

Na pulpicie aplikacji pasek usług pokazuje bieżący stan inicjalizacji komponentów.

## Windows installer

Official releases can include `SoundCore-Setup-<version>.exe`. The installer creates a per-user installation in `%LOCALAPPDATA%\Programs\SoundCore`, prepares Python 3.10 and the virtual environment, installs WebView2 and SoundCore dependencies, detects NVIDIA CUDA support, and creates Start menu / desktop shortcuts. Subsequent application updates continue to use SoundCore's built-in GitHub updater.

## Windows installer diagnostics

SoundCore 0.4.2+ creates `setup-bootstrap.log` before launching the environment bootstrap and `install.log` once PowerShell starts. If installation fails before `install.log` exists, inspect `setup-bootstrap.log` in the selected installation directory.


## 0.4.5 installer fix
The Windows installer bootstrap now uses collision-free PowerShell argument handling for venv, pip, PyTorch and runtime verification commands.


## 0.4.6 installer dependency stack

Windows installer uses Python 3.10 with numpy 1.22.0, scipy 1.11.4 and TTS 0.22.0.


## 0.4.8
- duży timer nagrywania dla referencji i próbek treningowych
- natychmiastowe odświeżanie biblioteki próbek i statystyk datasetu
- adaptacyjny eval split XTTS dla małych datasetów


## SoundCore 0.5.0

Wersja 0.5.0 rozwija cały workflow od zbierania datasetu do użycia wytrenowanego głosu. Sesja ciągła pozwala nagrywać tekst po tekście bez ręcznego uruchamiania każdej próbki. GPTTrainer raportuje do WebUI realną epokę, krok, loss, learning rate, historię wykresu oraz log techniczny zapisany również w profilu. Po zakończeniu fine-tuningu checkpoint można jednym przyciskiem podpiąć pod profil lub wrócić do bazowego XTTS v2. Aktualizacje są sprawdzane przez GitHub API i przygotowywane w tle przed restartem aplikacji.


## SoundCore 0.5.4

Wersja 0.5.2 poprawia ładowanie wytrenowanych modeli XTTS i zachowanie długich operacji UI. Fine-tunowany profil odtwarza wymagane ścieżki bazowych assetów XTTS przed inference, a synteza ponownie wyszukuje aktualny checkpoint na dysku. Aktualizacje są prezentowane jako nieblokująca karta w tle z realnym anulowaniem, a klawisz `Esc` służy do przerywania nagrywania i aktywnych okien/overlayów.

### Studio Syntezy i A/B (0.5.4)

Studio Syntezy jest pełnym panelem generowania: wybór modelu (aktywny/bazowy/wytrenowany), stylu, tempa i RVC. Test A/B zapisuje obie wersje do Historii syntezy, gdzie można je odsłuchać, wyeksportować do WAV lub usunąć. Nagrania mikrofonowe mają inteligentne zakończenie po ciszy, a inference wytrenowanego XTTS dzieli dłuższy tekst na zdania.


## SoundCore 0.7.1
Hotfix kompatybilności Python 3.10: naprawa startu modułu Song Studio po 0.7.0.

## Awaryjna naprawa / aktualizacja

Od wersji 0.7.2 SoundCore posiada niezależny updater awaryjny. Nie uruchamia on `main.py`, `gui.app`, XTTS ani modułów muzycznych, dlatego może naprawić instalację nawet wtedy, gdy główna aplikacja nie startuje.

Po instalacji dostępne są dwa skróty:

- **SoundCore** — normalne uruchomienie aplikacji,
- **SoundCore - Napraw - Aktualizuj** — sprawdzenie GitHuba, pobranie i reinstalacja najnowszego kodu.

Można też uruchomić ręcznie `repair_update.cmd` z katalogu SoundCore. Dane użytkownika i pobrane modele są zachowywane. Backup kodu trafia do `_repair_backups`.


## SoundCore 0.7.4

Instalator DiffRhythm pokazuje teraz na żywo log `pip`, postęp i aktywność procesu, nie otwiera pustego okna konsoli oraz może zostać przerwany z poziomu Song Studio.
