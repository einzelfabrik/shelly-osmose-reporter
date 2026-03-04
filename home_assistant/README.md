# Home Assistant Package

Dieses Paket stellt eine HA-Variante bereit mit:

- REST-Sensoren fuer Zulauf/Ablauf (Liters)
- Template-Sensor fuer Produktwasser
- Utility Meter fuer Tag/Woche/Monat
- Automation fuer taeglichen 06:00 Report (Vortag)
- Zusatzausgabe: Montag letzte Woche, am 1. letzter Monat

## Nutzung

1. Datei `home_assistant/package.yaml` nach `config/packages/osmose.yaml` kopieren.
2. In Home Assistant `packages` aktivieren (falls noch nicht aktiv).
3. WAHA/Telegram/SMTP Notification Service in HA konfigurieren.
4. In der Automation den gewuenschten `notify.*` Service eintragen.
