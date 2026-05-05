# Case `StackExchange/17`

- **Split**: train
- **Group**: StackExchange
- **Buggy lines**: 27  |  **Fixed lines**: 4
- **Lines changed** (del/add/mod): 0 / 0 / 25
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.1471

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0769** (P=1.0, R=0.04)
- Edits produced: 1
- Rules fired: `R6`

## Buggy source

```python
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute
import random

n = 8
gate_list = ['u1', 'u2', 'u3', 'id', 'x', 'y', 'z', 'h', 's'] 

selected_gates= []

for i in range(0,8):
  x = random.choice(gates)
  a = '({})'.format(i)
  k = x+a
  selected_gates.append(k)

print(selected_gates)
qr = QuantumCircuit(n)
qr.selected_gates[0]
qr.selected_gates[1]
qr.selected_gates[2]
qr.selected_gates[3]
qr.selected_gates[4]
qr.selected_gates[5]
qr.selected_gates[6]
qr.selected_gates[7]

qr.draw()
```

## Fixed source (human gold)

```python
from qiskit.circuit.random import random_circuit

qr = random_circuit(10, 10, max_operands=3, measure=True)
qr.draw()
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,27 +1,4 @@
-from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
-from qiskit import Aer, execute
-import random
+from qiskit.circuit.random import random_circuit
 
-n = 8
-gate_list = ['u1', 'u2', 'u3', 'id', 'x', 'y', 'z', 'h', 's'] 
-
-selected_gates= []
-
-for i in range(0,8):
-  x = random.choice(gates)
-  a = '({})'.format(i)
-  k = x+a
-  selected_gates.append(k)
-
-print(selected_gates)
-qr = QuantumCircuit(n)
-qr.selected_gates[0]
-qr.selected_gates[1]
-qr.selected_gates[2]
-qr.selected_gates[3]
-qr.selected_gates[4]
-qr.selected_gates[5]
-qr.selected_gates[6]
-qr.selected_gates[7]
-
+qr = random_circuit(10, 10, max_operands=3, measure=True)
 qr.draw()
```
