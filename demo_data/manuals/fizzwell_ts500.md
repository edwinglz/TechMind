# Fizzwell Systems FlowTouch TS-500 Self-Serve Dispenser: Service Manual

Model TS-500. Self-serve touchscreen beverage dispenser with integrated refrigeration, onboard carbonator, and a single multi-flavor nozzle cluster serving up to 24 flavors. Rev. 5.0.

## System overview

### Water supply

Water enters through a 3/8 in. inlet and inlet strainer, then splits to the onboard carbonator and the still-water circuit.

### CO2 and regulators

An external CO2 cylinder feeds the onboard carbonator through the primary regulator (90-100 psi) and the BIB pumps through a secondary regulator (60-70 psi). The controller watches CO2 pressure and shows E-21 when it is low.

### Carbonator pump

A compact carbonator pump fills the internal carbonator tank. If a fill takes longer than 3 minutes the controller shows E-61.

### Bag-in-box syrup pumps

Each flavor has a BIB pump on the syrup rack. A sold-out sensor on each line shows E-12 and greys the flavor out on screen when its bag is empty.

### Cold plate and ice bin

The TS-500 does not use a cold plate. A refrigeration deck with a condenser fan (P-TSFAN) chills a water bath that cools the beverage lines. Ice is dispensed by a separate ice machine.

### Valves and nozzles

All flavors pour through one nozzle cluster. Each flavor path has a solenoid valve (P-SOL) and seal kit (P-VSEAL). The drip tray has a level sensor (E-50).

## Installation and pressures

| Item | Setting |
|---|---|
| Incoming water pressure | 40-60 psi, minimum 30 psi |
| CO2 primary regulator | 90-100 psi |
| CO2 secondary regulator | 60-70 psi |
| Target drink temperature | 40 degrees F or colder |
| Condenser clearance | 6 in. on both sides |
| Power | 115 V, dedicated 20 A circuit |

## Brix calibration

1. On the service screen (technician PIN), choose Calibrate > Brix and pick the flavor.
2. Hold the brix cup under the nozzle cluster; the unit pours syrup and water separately.
3. Adjust the flavor's syrup value on screen until the ratio matches the supplier's spec (usually 5:1).
4. Save and taste-test.

## Daily and weekly cleaning

**Daily (store staff):** remove the nozzle cluster cap by hand, soak in warm sanitizer water for 10 minutes, refit; wipe the touchscreen with a damp cloth; empty the drip tray.

**Weekly (store staff):** check that the condenser vents are not blocked by boxes.

**Quarterly (technician):** clean condenser coils, check pressures, sanitize syrup lines.

## Troubleshooting

### No carbonation (flat drinks)

| Symptom | Likely cause | Action |
|---|---|---|
| E-21 shown | CO2 cylinder empty or valve closed | Open the valve or swap the cylinder |
| E-61 shown | Carbonator pump not filling | Check water pressure and inlet strainer; service the pump |
| Flat and warm | Refrigeration warm | See Warm drinks |

### Watery or syrupy drinks

| Symptom | Likely cause | Action |
|---|---|---|
| E-12, flavor greyed out | Bag-in-box empty | Replace the bag |
| One flavor off-taste | Brix drifted | Recalibrate |

### No flow on one valve

| Symptom | Likely cause | Action |
|---|---|---|
| E-34 shown, clicking | Solenoid coil failed | Replace P-SOL |
| No code | Nozzle cluster blocked | Clean nozzle cluster |

### No flow on all valves

| Symptom | Likely cause | Action |
|---|---|---|
| Screen dark | No power or breaker tripped | Check plug; reset breaker once |
| Screen on, nothing pours | Water supply off | Open supply |

### Foaming

Usually warm drinks (E-40) or CO2 primary pressure set too high.

### Warm drinks

| Symptom | Likely cause | Action |
|---|---|---|
| E-40 shown, fan not running | Condenser fan failed | Replace P-TSFAN |
| E-40 shown, fan running | Condenser coils clogged with dust | Clean coils |
| Vents blocked | Boxes against the unit | Clear 6 in. around the vents |

E-40 is most common in summer when back-of-house temperatures are high.

### Leaks

| Symptom | Likely cause | Action |
|---|---|---|
| Drip under nozzle cluster, E-50 | Worn valve seal or O-ring | Replace P-VSEAL kit |
| Water under unit | Water bath overflow line loose | Reconnect line |

### No ice

The TS-500 does not dispense ice; see the ice machine manual.

## Error codes

| Code | Meaning | First action |
|---|---|---|
| E-12 | Flavor sold out (bag empty) | Replace the bag-in-box for that flavor |
| E-21 | Low CO2 pressure | Check the cylinder valve and gauge |
| E-34 | Valve solenoid fault | Technician: check connector, replace solenoid |
| E-40 | Refrigeration warm | Technician: check condenser fan and coils |
| E-50 | Drip tray full or leak detected | Empty the tray; if it refills quickly, call service |
| E-61 | Carbonator fill timeout | Technician: check water supply and carbonator pump |
| E-90 | Controller fault | Power-cycle once; if it returns, replace controller |

## Safety

- **CO2 asphyxiation:** if a CO2 leak is suspected, ventilate and leave the area.
- **High-pressure gas:** never loosen pressurized fittings.
- **Electrical:** only technicians open the front service panel; unplug first.
- **Sanitation:** clean the nozzle cluster daily; mold is a health hazard.
