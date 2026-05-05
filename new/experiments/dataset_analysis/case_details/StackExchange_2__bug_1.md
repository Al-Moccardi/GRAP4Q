# Case `StackExchange_2/bug_1`

- **Split**: test
- **Group**: StackExchange_2
- **Buggy lines**: 5  |  **Fixed lines**: 5
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.7143

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **1.0** (P=1.0, R=1.0)
- Edits produced: 1
- Rules fired: `R4`

## Buggy source

```python
from qiskit import *

circuit = QuantumCircuit(1)
circuit.iden(0)
print(circuit)
```

## Fixed source (human gold)

```python
from qiskit import *

circuit = QuantumCircuit(1)
circuit.id(0)
print(circuit)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -2,4 +2,4 @@
 
 circuit = QuantumCircuit(1)
-circuit.iden(0)
+circuit.id(0)
 print(circuit)
```
