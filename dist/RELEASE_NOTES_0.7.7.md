# SoundCore 0.7.7

## DiffRhythm
- Naprawiono `AttributeError: LanguageIdentifier has no attribute from_pickled_model`.
- Runtime DiffRhythm automatycznie sprawdza wymagane API i w razie potrzeby instaluje `py3langid==0.2.2`.
- Naprawa istniejÄ…cego runtime odbywa siÄ™ automatycznie przed renderem, bez kasowania modeli i Ĺ›rodowiska.

## Interfejs
- UsuniÄ™to czarne tĹ‚a z logu DiffRhythm, Planu wokalu/LRC i logu treningu XTTS.
- Panele diagnostyczne sÄ… zgodne z jasnym wyglÄ…dem SoundCore.
- Przyciski pobierania/naprawy DiffRhythm i eSpeak NG nie sÄ… juĹĽ ciemnymi przyciskami.

# SoundCore 0.7.6

## Continuous recording / audio reliability
- ZwiÄ™kszono przerwÄ™ miÄ™dzy kolejnymi prĂłbami sesji ciÄ…gĹ‚ej do ok. 3 sekund.
- Nagrywanie uĹĽywa teraz osobnego `sounddevice.InputStream` dla kaĹĽdej prĂłbki zamiast globalnego `sd.rec()/sd.stop()`.
- Mikrofon jest otwierany w natywnej czÄ™stotliwoĹ›ci urzÄ…dzenia, a prĂłbka jest bezpiecznie resamplowana do 22050 Hz.
- Dodano blokadÄ™ wejĹ›cia audio i krĂłtki czas zwolnienia WASAPI/PortAudio pomiÄ™dzy prĂłbami.
- Dodano kontrolÄ™ jakoĹ›ci: mocno przesterowana albo praktycznie pusta prĂłbka nie trafia do datasetu.

## DiffRhythm
- Naprawiono `ModuleNotFoundError: No module named 'model'` przez uruchamianie inferencji z katalogu gĹ‚Ăłwnego repo i ustawienie `PYTHONPATH`.
- Generowanie DiffRhythm nie otwiera juĹĽ okna konsoli/PowerShell.
- stdout/stderr pozostaje widoczny na ĹĽywo wyĹ‚Ä…cznie w logu Song Studio.

## CzytelnoĹ›Ä‡ UI
- Konfiguracja muzyki jest pokazana jako 3 kroki: DiffRhythm â†’ eSpeak NG â†’ modele AI.
- Log DiffRhythm, Plan wokalu/LRC i log treningu XTTS majÄ… spĂłjny ciemny wyglÄ…d konsoli.
- UporzÄ…dkowano nazwy przyciskĂłw instalacji i statusy zaleĹĽnoĹ›ci.

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
