# Case `Cirq/3`

- **Split**: train
- **Group**: Cirq
- **Buggy lines**: 23  |  **Fixed lines**: 23
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.8636

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
import cirq
import numpy as np

qubits = cirq.LineQubit.range(2)

circuit = cirq.Circuit()

circuit.append(cirq.X(qubits[0]))
circuit.append(cirq.Z(qubits[1]))

s = cirq.DensityMatrixSimulator()

results = s.simulate(circuit)

r = cirq.DensityMatrixSimulator()

circuit2 = cirq.Circuit()

circuit2.append(cirq.X(qubits[0]))

circuit2.append(cirq.Z(qubits[1]))

results2 =r.simulate(circuit2, initial_state = results._final_simulator_state.density_matrix)
```

## Fixed source (human gold)

```python
import cirq
import numpy as np

qubits = cirq.LineQubit.range(2)

circuit = cirq.Circuit()

circuit.append(cirq.X(qubits[0]))
circuit.append(cirq.Z(qubits[1]))

s = cirq.DensityMatrixSimulator()

results = s.simulate(circuit)

r = cirq.DensityMatrixSimulator()

circuit2 = cirq.Circuit()

circuit2.append(cirq.X(qubits[0]))

circuit2.append(cirq.Z(qubits[1]))

results2 =r.simulate(circuit2, initial_state = results.final_density_matrix)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -21,3 +21,3 @@
 circuit2.append(cirq.Z(qubits[1]))
 
-results2 =r.simulate(circuit2, initial_state = results._final_simulator_state.density_matrix)
+results2 =r.simulate(circuit2, initial_state = results.final_density_matrix)
```
