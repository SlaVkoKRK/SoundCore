# SoundCore 0.7.5

## eSpeak NG installer fix
- Naprawiono wykrywanie oficjalnego instalatora eSpeak NG 1.52.0 dla Windows.
- SoundCore obsĹ‚uguje teraz bieĹĽÄ…cÄ… nazwÄ™ `espeak-ng.msi`.
- Dodano fallback dla starszych nazw `*x64*.msi` oraz dowolnego oficjalnego pliku `.msi`.
- Komunikat instalatora nie zakĹ‚ada juĹĽ, ĹĽe nazwa pliku musi zawieraÄ‡ `x64`.

# SoundCore 0.7.4

## Automatyczna instalacja eSpeak NG
- W Song Studio pojawiĹ‚ siÄ™ przycisk â€žPobierz i zainstaluj eSpeak NGâ€ť, gdy biblioteka nie jest wykryta.
- SoundCore pobiera oficjalny instalator x64 z najnowszego wydania `espeak-ng/espeak-ng` na GitHubie.
- Instalator MSI uruchamia siÄ™ bez rÄ™cznego szukania pliku.
- Po instalacji SoundCore automatycznie ponownie wykrywa `libespeak-ng.dll` i odĹ›wieĹĽa status DiffRhythm.
- Stan pobierania i instalacji eSpeak NG jest widoczny w Song Studio.

# SoundCore 0.7.3

## DiffRhythm installer hotfix

- instalacja zaleĹĽnoĹ›ci DiffRhythm pokazuje teraz ĹĽywy log z `pip` w Song Studio
- postÄ™p nie zatrzymuje siÄ™ juĹĽ sztucznie na 52%; aktualizuje siÄ™ w trakcie pobierania/budowania/instalacji pakietĂłw
- pokazuje czas instalacji i czas od ostatniej aktywnoĹ›ci procesu
- procesy `pip`/venv dziaĹ‚ajÄ… bez pustego okna konsoli w Windows
- dodano przycisk **Przerwij instalacjÄ™** z bezpiecznym zakoĹ„czeniem procesu pip
- bĹ‚Ä™dy pip pozostajÄ… widoczne w logu Song Studio
- zachowano izolowane Ĺ›rodowisko DiffRhythm w `engine_runtime/music/diffrhythm`
