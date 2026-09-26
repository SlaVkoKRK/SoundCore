# SoundCore 0.4.5

- Fixed Windows installer bootstrap argument passing.
- Renamed the PowerShell `Run` parameter from `$Args` to `$Arguments` to avoid collision with PowerShell's automatic `$args` variable.
- Native Python/pip commands are now invoked directly with an argument array, preserving paths and values exactly.
- All bootstrap commands now use explicit named parameters.
