# Eurotherm Smart365 per Home Assistant

Integrazione custom (installabile da HACS) per il sistema radiante **Eurotherm SmartComfort 365**.
Comunica **in locale** con il pannello touch tramite **Modbus TCP** (porta 502): niente cloud, niente credenziali dell'app.

## Cosa crea

- **Un termostato per ogni stanza**, trovata in automatico: temperatura attuale, umidità (se il sensore la misura) e temperatura obiettivo.
  - `Automatico` segue il programma settimanale del pannello.
  - `Riscaldamento`/`Raffrescamento` corrisponde alla modalità **manuale**: cambiando la temperatura da Home Assistant la stanza passa in manuale. Per tornare al programma scegli di nuovo `Automatico`.
- **Per ogni zona**: modalità (A casa / Spento / Fuori casa; Vacanza è solo in lettura), stagione (Riscaldamento / Raffrescamento) e boost ricambio aria (disattivato di default, serve solo con unità aria).
- **Sensori**: temperatura esterna, temperatura e setpoint di mandata dei moduli, temperatura obiettivo, punto di rugiada, batteria scarica, guasto sensore, condensa.

Le stanze si chiamano "Stanza 1", "Stanza 2"… nell'ordine del modulo: rinominale dalla pagina del dispositivo in Home Assistant confrontando le temperature con l'app Smart365.

## Installazione

1. In HACS: menu ⋮ → **Repository personalizzati** → URL `https://github.com/pls70/ha-eurotherm-smart365`, tipo **Integrazione**.
2. Cerca "Eurotherm Smart365", installa e riavvia Home Assistant.
3. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Eurotherm Smart365** e inserisci l'IP del pannello (lo trovi sul pannello in Impostazioni → Rete).

Consiglio: assegna al pannello un IP fisso (riserva DHCP sul router).

## Limiti noti

- Il protocollo Modbus non espone se una stanza sta "chiamando calore".
- Lo spegnimento è per zona, non per singola stanza.
- La modalità vacanza si imposta solo dal pannello o dall'app.

Mappa registri: *SmartComfort 365 – Modbus interface for home automation*, Rev.05 (Eurotherm).
Progetto non affiliato a Eurotherm.
