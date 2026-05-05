# Case `StackExchange/7`

- **Split**: val
- **Group**: StackExchange
- **Buggy lines**: 7  |  **Fixed lines**: 15
- **Lines changed** (del/add/mod): 0 / 4 / 6
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.4783

## QChecker static analysis

3 finding(s); rules fired: `QC01,QC03,QC04`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
result = execute(circuit, backend, shots=1000).result()
counts  = result.get_counts(circuit)
print(counts)
```

## Fixed source (human gold)

```python
from qiskit import *
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)

# Retrieve the statevector_simulator backend
backend = Aer.get_backend('statevector_simulator')

result = execute(circuit, backend, shots=1000).result()

# Get the statevector from result().
statevector = result.get_statevector(circuit)
print(statevector)

# Normalize statevector to receive the true probabilities.
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -3,5 +3,13 @@
 circuit.h(0)
 circuit.cx(0, 1)
+
+# Retrieve the statevector_simulator backend
+backend = Aer.get_backend('statevector_simulator')
+
 result = execute(circuit, backend, shots=1000).result()
-counts  = result.get_counts(circuit)
-print(counts)
+
+# Get the statevector from result().
+statevector = result.get_statevector(circuit)
+print(statevector)
+
+# Normalize statevector to receive the true probabilities.
```
