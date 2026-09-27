# SoundCore 0.8.0

## DiffRhythm CUDA repair
- Naprawiono `WinError 5: Odmowa dostępu` podczas podmiany CPU-only PyTorch na build CUDA.
- Przed naprawą CUDA SoundCore zatrzymuje aktywny render i czeka na zamknięcie procesu inferencji.
- SoundCore kończy wyłącznie procesy Pythona uruchomione z prywatnego venv DiffRhythm.
- Dodano kontrolę zwolnienia `torch/_C*.pyd` przed uruchomieniem pip.
- Usuwane są pozostałości po przerwanych instalacjach pip, np. katalogi `~orch*`.
- Po instalacji nadal wykonywana jest weryfikacja `torch.cuda.is_available()` oraz nazwy GPU.

# SoundCore 0.7.9

## DiffRhythm CUDA
- Naprawiono CPU-only PyTorch w izolowanym runtime DiffRhythm.
- SoundCore wykrywa teraz CUDA bezpośrednio wewnątrz venv DiffRhythm.
- Dodano przycisk „Napraw CUDA dla DiffRhythm”.
- Naprawa instaluje zgodny PyTorch 2.6.0 / torchvision 0.21.0 / torchaudio 2.6.0 z CUDA 12.4.
- Render na komputerze z NVIDIA jest blokowany, jeśli runtime DiffRhythm nadal ma CPU-only PyTorch.
- Song Studio pokazuje PyTorch runtime, GPU, wersję CUDA oraz G2P/ONNX.
- Instalacja świeżego DiffRhythm automatycznie naprawia runtime CUDA, jeśli wykryje kartę NVIDIA.

# SoundCore 0.7.8

## Model downloader DiffRhythm
- Modele są jawnie pobierane przed startem inferencji.
- SoundCore doinstalowuje `hf_xet` w izolowanym venv DiffRhythm.
- Osobny postęp dla CFM, MuQ-MuLan, MuQ audio, XLM-R i VAE.
- Widoczne MB/GB, procent, aktualny plik i prędkość pobierania.
- Render startuje dopiero po zakończeniu prefetchu modeli.
- STOP przerywa również pobieranie modeli.

# SoundCore 0.7.7

## DiffRhythm
- Naprawiono `AttributeError: LanguageIdentifier has no attribute from_pickled_model`.
- Runtime DiffRhythm automatycznie sprawdza wymagane API i w razie potrzeby instaluje `py3langid==0.2.2`.
- Naprawa istniejącego runtime odbywa się automatycznie przed renderem, bez kasowania modeli i środowiska.

## Interfejs
- Usunięto czarne tła z logu DiffRhythm, Planu wokalu/LRC i logu treningu XTTS.
- Panele diagnostyczne są zgodne z jasnym wyglądem SoundCore.
- Przyciski pobierania/naprawy DiffRhythm i eSpeak NG nie są już ciemnymi przyciskami.

# SoundCore 0.7.6

## Continuous recording / audio reliability
- Zwiększono przerwę między kolejnymi próbami sesji ciągłej do ok. 3 sekund.
- Nagrywanie używa teraz osobnego `sounddevice.InputStream` dla każdej próbki zamiast globalnego `sd.rec()/sd.stop()`.
- Mikrofon jest otwierany w natywnej częstotliwości urządzenia, a próbka jest bezpiecznie resamplowana do 22050 Hz.
- Dodano blokadę wejścia audio i krótki czas zwolnienia WASAPI/PortAudio pomiędzy próbami.
- Dodano kontrolę jakości: mocno przesterowana albo praktycznie pusta próbka nie trafia do datasetu.

## DiffRhythm
- Naprawiono `ModuleNotFoundError: No module named 'model'` przez uruchamianie inferencji z katalogu głównego repo i ustawienie `PYTHONPATH`.
- Generowanie DiffRhythm nie otwiera już okna konsoli/PowerShell.
- stdout/stderr pozostaje widoczny na żywo wyłącznie w logu Song Studio.

## Czytelność UI
- Konfiguracja muzyki jest pokazana jako 3 kroki: DiffRhythm → eSpeak NG → modele AI.
- Log DiffRhythm, Plan wokalu/LRC i log treningu XTTS mają spójny ciemny wygląd konsoli.
- Uporządkowano nazwy przycisków instalacji i statusy zależności.

# SoundCore 0.7.4

## Automatyczna instalacja eSpeak NG
- W Song Studio pojawił się przycisk „Pobierz i zainstaluj eSpeak NG”, gdy biblioteka nie jest wykryta.
- SoundCore pobiera oficjalny instalator x64 z najnowszego wydania `espeak-ng/espeak-ng` na GitHubie.
- Instalator MSI uruchamia się bez ręcznego szukania pliku.
- Po instalacji SoundCore automatycznie ponownie wykrywa `libespeak-ng.dll` i odświeża status DiffRhythm.
- Stan pobierania i instalacji eSpeak NG jest widoczny w Song Studio.

# SoundCore 0.7.3

## DiffRhythm installer hotfix

- instalacja zależności DiffRhythm pokazuje teraz żywy log z `pip` w Song Studio
- postęp nie zatrzymuje się już sztucznie na 52%; aktualizuje się w trakcie pobierania/budowania/instalacji pakietów
- pokazuje czas instalacji i czas od ostatniej aktywności procesu
- procesy `pip`/venv działają bez pustego okna konsoli w Windows
- dodano przycisk **Przerwij instalację** z bezpiecznym zakończeniem procesu pip
- błędy pip pozostają widoczne w logu Song Studio
- zachowano izolowane środowisko DiffRhythm w `engine_runtime/music/diffrhythm`
