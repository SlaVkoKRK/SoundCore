# SoundCore 0.3.5

## UI
- jasny, subtelny scrollbar zamiast czarnego paska WebView2 przy zmaksymalizowanym oknie,
- dodatkowe sekcje tekstu do czytania w Profilach głosu i Treningu modelu,
- możliwość utworzenia profilu bez opuszczania zakładki Trening modelu.

## Dynamiczne teksty nagraniowe
- nowa lokalna baza polskich tekstów podzielona na kategorie: naturalne, fonetyczne, liczby, pytania, prozodia i techniczne,
- tekst jest składany dynamicznie do zadanej długości nagrania,
- profil referencyjny preferuje naturalną, ciągłą mowę,
- dataset treningowy rotuje materiał fonetyczny i prozodyczny,
- przy zmianie czasu próbki tekst przelicza się automatycznie,
- przycisk „Inny tekst” / „Następny tekst” pobiera kolejny wariant z backendu.
