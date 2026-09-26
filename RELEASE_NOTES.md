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
