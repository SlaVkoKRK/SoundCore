# SoundCore 0.7.3

## DiffRhythm installer hotfix

- instalacja zależności DiffRhythm pokazuje teraz żywy log z `pip` w Song Studio
- postęp nie zatrzymuje się już sztucznie na 52%; aktualizuje się w trakcie pobierania/budowania/instalacji pakietów
- pokazuje czas instalacji i czas od ostatniej aktywności procesu
- procesy `pip`/venv działają bez pustego okna konsoli w Windows
- dodano przycisk **Przerwij instalację** z bezpiecznym zakończeniem procesu pip
- błędy pip pozostają widoczne w logu Song Studio
- zachowano izolowane środowisko DiffRhythm w `engine_runtime/music/diffrhythm`
