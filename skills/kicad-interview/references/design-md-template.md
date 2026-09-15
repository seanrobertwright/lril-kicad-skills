# <Project name> - design document

Status: draft | approved (date)
Owner: <user>
Revision: A

## 1. Purpose

One paragraph. Must-work function. Environment. Quantity. Budget. Deadline.

## 2. Requirements

| id | requirement | source | status |
|----|-------------|--------|--------|
| R1 | ... | user | decided |

## 3. Power tree

Input -> protection -> regulator -> rail (V, Imax, load list, margin).

| rail | source | regulator (MPN) | Imax budget | loads | notes |
|------|--------|-----------------|-------------|-------|-------|

Computations (formula, inputs, result, chosen value):

- ...

## 4. Parts

| ref | function | MPN | symbol (Lib:Name) | footprint (Lib:Name) | distributor # | why | alternatives | datasheet |
|-----|----------|-----|-------------------|----------------------|---------------|-----|--------------|-----------|

## 5. Connectors and interfaces

| ref | connector MPN | purpose | pinout (pin: net) | protection | mating part |
|-----|---------------|---------|-------------------|------------|-------------|

## 6. Pin plan

For every IC: table of pin -> net / NC (with datasheet guidance for unused pins).

## 7. Mechanical

Size, shape, mounting holes (positions, size), height limits, keep-outs, enclosure.

## 8. PCB technology

Layers, stackup, thickness, copper, finish, mask/silk colours, min track/space/via,
net classes (widths/clearances), impedance-controlled nets.

## 9. Manufacturing and assembly

Fab, assembly service, quantity, sides assembled, fiducials, panel, silkscreen content.

## 10. Test and bring-up

Test points, LEDs, jumpers, bring-up sequence.

## 11. Compliance

ESD, EMC, temperature, safety, RoHS.

## 12. Decision log

| id | decision | source | date |
|----|----------|--------|------|

## 13. Open questions

- (none)
