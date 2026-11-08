# Eurotherm Smart365 per Home Assistant

Integrazione custom (installabile da HACS) per il sistema radiante **Eurotherm SmartComfort 365**.
Comunica **in locale** con il pannello touch tramite **Modbus TCP** (porta 502): niente cloud, niente credenziali dell'app.

## Cosa crea

- **Un termostato per ogni stanza**, trovata in automatico: temperatura attuale, umidità (se il sensore la misura) e temperatura obiettivo.
  - `Automatico` segue il programma settimanale del pannello.
  - `Riscaldamento`/`Raffrescamento` corrisponde alla modalità **manuale**: cambiando la temperatura da Home Assistant la stanza passa in manuale. Per tornare al programma scegli di nuovo `Automatico`.
- **Programma settimanale in Home Assistant** (facoltativo, vedi sotto).
- **Per ogni zona**: modalità (A casa / Spento / Fuori casa; Vacanza è solo in lettura), stagione (Riscaldamento / Raffrescamento) e boost ricambio aria (disattivato di default, serve solo con unità aria).
- **Sensori**: temperatura esterna, temperatura e setpoint di mandata dei moduli, temperatura obiettivo, punto di rugiada, batteria scarica, guasto sensore, condensa.

Le stanze si chiamano "Stanza 1", "Stanza 2"… nell'ordine del modulo: rinominale dalla pagina del dispositivo in Home Assistant confrontando le temperature con l'app Smart365.

## Installazione

1. In HACS: menu ⋮ → **Repository personalizzati** → URL `https://github.com/pls70/ha-eurotherm-smart365`, tipo **Integrazione**.
2. Cerca "Eurotherm Smart365", installa e riavvia Home Assistant.
3. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Eurotherm Smart365** e inserisci l'IP del pannello (lo trovi sul pannello in Impostazioni → Rete).

Consiglio: assegna al pannello un IP fisso (riserva DHCP sul router).

## Programma settimanale gestito da Home Assistant

Il pannello **non espone via Modbus il suo programma settimanale** (né le fasce né le temperature dei livelli). In alternativa l'integrazione può far girare il programma in Home Assistant, con la stessa logica a 3 livelli del pannello:

- **Programma livello 1 / 2 / 3** (entità numero, per zona): la temperatura di ciascun livello. Default 17 / 20 / 21 °C.
- **Programmazione livello 2** e **livello 3**: due helper *Programmazione* di Home Assistant in cui disegni le fasce della settimana. Dove è attivo il livello 3 vale il livello 3, altrimenti dove è attivo il livello 2 vale il livello 2, altrimenti il livello 1.
- **Programma Home Assistant** (interruttore, per zona): acceso, a ogni cambio di livello le stanze della zona passano in *manuale* alla temperatura del livello; spento, le stanze tornano al programma del pannello.
- **Livello programma** (sensore, per zona): il livello attivo adesso.
- **Altri termostati** (facoltativo): condizionatori, stufette o qualsiasi entità `climate` di altre integrazioni possono seguire lo stesso programma. Ricevono la temperatura del livello solo quando sono accesi in riscaldamento (o automatico), e non vengono mai accesi o spenti. Se ne accendi uno, prende subito la temperatura del livello attivo.

Configurazione:
1. **Impostazioni → Dispositivi e servizi → Aiutanti → Crea aiutante → Programmazione**: crea "Livello 2" e "Livello 3" e disegna le fasce.
2. **Impostazioni → Dispositivi e servizi → Eurotherm Smart365 → Configura**: collega i due helper alla zona e, se vuoi, scegli gli altri termostati.
3. Imposta le temperature dei 3 livelli nella pagina del dispositivo "Zona 1" e accendi **Programma Home Assistant**.

Da sapere:
- Il programma agisce solo con la zona in *A casa* e in *Riscaldamento*. Le stanze spente o in modalità speciali del pannello (party, notte…) non vengono toccate.
- Se cambi a mano la temperatura di una stanza, resta così fino al prossimo cambio di livello.
- Se Home Assistant si ferma, le stanze restano all'ultima temperatura impostata. Spegnendo l'interruttore tornano al programma del pannello.

## Diagnostica: leggere i registri grezzi

L'azione **Eurotherm Smart365: Leggi registri** (`eurotherm_smart365.read_registers`) legge registri Modbus qualsiasi e restituisce i valori, senza scrivere nulla. Serve a esplorare parti della mappa non ancora usate dall'integrazione (per esempio il programma settimanale). Da **Strumenti per sviluppatori → Azioni**:

```yaml
action: eurotherm_smart365.read_registers
data:
  address: 100
  count: 130
```

I registri che il pannello rifiuta compaiono come `null`.

## Limiti noti

- Il protocollo Modbus non espone se una stanza sta "chiamando calore".
- Lo spegnimento è per zona, non per singola stanza.
- La modalità vacanza si imposta solo dal pannello o dall'app.
- Il programma settimanale del pannello non si legge né si modifica via Modbus (vedi sopra per l'alternativa in Home Assistant).

Mappa registri: *SmartComfort 365 – Modbus interface for home automation*, Rev.05 (Eurotherm).
Progetto non affiliato a Eurotherm.
