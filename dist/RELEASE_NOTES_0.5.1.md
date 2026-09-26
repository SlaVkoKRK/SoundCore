# SoundCore 0.5.1

- Naprawiono bĹ‚Ä…d finalizacji treningu `expected str, bytes or os.PathLike object, not NoneType`.
- `trainer.output_path=None` nie powoduje juĹĽ `Path(None)` po zakoĹ„czeniu treningu.
- Dodano bezpieczny fallback do katalogu profilu oraz rekursywne wyszukiwanie `best_model.pth`, `checkpoint_*.pth` i `config.json`.
- Udany trening nie jest oznaczany jako bĹ‚Ä…d tylko dlatego, ĹĽe Coqui nie zwrĂłciĹ‚o Ĺ›cieĹĽki `output_path`.
