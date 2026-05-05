# Case `Cirq/6`

- **Split**: train
- **Group**: Cirq
- **Buggy lines**: 15  |  **Fixed lines**: 15
- **Lines changed** (del/add/mod): 0 / 0 / 2
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.913

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
import random
import numpy as np
import cirq

circuit, circuit2, circuit3   = cirq.Circuit()
p = 0.2
q = 0.1
r = 0.3
alice, bob, charlie = cirq.LineQubit.range(1, 4)
rho_12 = circuit.append([cirq.H(alice), cirq.CNOT(alice, bob)]) 
#circuit.append([cirq.H(alice), cirq.CNOT(alice, bob)]) 
rho_23 = circuit.append([cirq.H(bob), cirq.CNOT(bob, charlie)]) 
rho_13 = circuit.append([cirq.H(alice), cirq.CNOT(alice, charlie)]) 
circuit = rho_12 + rho_23 + rho_13
print(circuit)
```

## Fixed source (human gold)

```python
import random
import numpy as np
import cirq

circuit= cirq.Circuit()
p = 0.2
q = 0.1
r = 0.3
alice, bob, charlie = cirq.LineQubit.range(1, 4)
rho_12 = circuit.append([cirq.H(alice), cirq.CNOT(alice, bob)]) 
#circuit.append([cirq.H(alice), cirq.CNOT(alice, bob)]) 
rho_23 = circuit.append([cirq.H(bob), cirq.CNOT(bob, charlie)]) 
rho_13 = circuit.append([cirq.H(alice), cirq.CNOT(alice, charlie)]) 
#circuit = rho_12 + rho_23 + rho_13
print(circuit)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -3,5 +3,5 @@
 import cirq
 
-circuit, circuit2, circuit3   = cirq.Circuit()
+circuit= cirq.Circuit()
 p = 0.2
 q = 0.1
@@ -12,4 +12,4 @@
 rho_23 = circuit.append([cirq.H(bob), cirq.CNOT(bob, charlie)]) 
 rho_13 = circuit.append([cirq.H(alice), cirq.CNOT(alice, charlie)]) 
-circuit = rho_12 + rho_23 + rho_13
+#circuit = rho_12 + rho_23 + rho_13
 print(circuit)
```
