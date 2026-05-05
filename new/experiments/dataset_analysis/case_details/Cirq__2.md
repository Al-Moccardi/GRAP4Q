# Case `Cirq/2`

- **Split**: train
- **Group**: Cirq
- **Buggy lines**: 26  |  **Fixed lines**: 26
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.9

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

qubits = [cirq.GridQubit(0,0), cirq.GridQubit(0,1)]
circuit = cirq.Circuit([cirq.ry(np.pi/2).on(qubits[0]),
                        cirq.ISWAP(qubits[0], qubits[1]) ** 0.5,
                        cirq.ry(np.pi/2).on(qubits[1])])

print(circuit)
qubits = [cirq.GridQubit(1,1), cirq.GridQubit(1,2)]
circuit2 = cirq.Circuit([cirq.ry(np.pi/2).on(qubits[0]),
                        cirq.ISWAP(qubits[0], qubits[1]) ** 0.5,
                        cirq.ry(np.pi/2).on(qubits[1])])
circuit2.append(circuit, strategy=cirq.InsertStrategy.EARLIEST)
print()
print()
print(circuit2)

circuit3 = cirq.Circuit([cirq.ry(np.pi/2).on(qubits[0]),
                        cirq.ISWAP(qubits[0], qubits[1]) ** 0.5,
                        cirq.ry(np.pi/2).on(qubits[1])])

circuit3.insert(0, circuit, strategy=cirq.InsertStrategy.EARLIEST)
print()
print()
print(circuit3)
```

## Fixed source (human gold)

```python
import cirq
import numpy as np

qubits = [cirq.GridQubit(0,0), cirq.GridQubit(0,1)]
circuit = cirq.Circuit([cirq.ry(np.pi/2).on(qubits[0]),
                        cirq.ISWAP(qubits[0], qubits[1]) ** 0.5,
                        cirq.ry(np.pi/2).on(qubits[1])])

print(circuit)
qubits = [cirq.GridQubit(1,1), cirq.GridQubit(1,2)]
circuit2 = cirq.Circuit([cirq.ry(np.pi/2).on(qubits[0]),
                        cirq.ISWAP(qubits[0], qubits[1]) ** 0.5,
                        cirq.ry(np.pi/2).on(qubits[1])])
circuit2.append(circuit, strategy=cirq.InsertStrategy.EARLIEST)
print()
print()
print(circuit2)

circuit3 = cirq.Circuit([cirq.ry(np.pi/2).on(qubits[0]),
                        cirq.ISWAP(qubits[0], qubits[1]) ** 0.5,
                        cirq.ry(np.pi/2).on(qubits[1])])

circuit3.insert(0, circuit, strategy=cirq.InsertStrategy.EARLIEST)
print()
print()
print(cirq.Circuit.zip(circuit, circuit2))  # print(circuit + circuit2.all_operations())
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -24,3 +24,3 @@
 print()
 print()
-print(circuit3)
+print(cirq.Circuit.zip(circuit, circuit2))  # print(circuit + circuit2.all_operations())
```
