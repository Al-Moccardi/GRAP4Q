# Case `StackExchange/1`

- **Split**: train
- **Group**: StackExchange
- **Buggy lines**: 12  |  **Fixed lines**: 13
- **Lines changed** (del/add/mod): 0 / 2 / 8
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.5909

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *
#definitions
q = QuantumRegister(1)
c = ClassicalRegister(2)
qc = QuantumCircuit(q,c)

# building the circuit
qc.h(q)
qc.measure(q[0],c[0])
qc.x(q[0]).c[0]_if(c[0], 0)
qc.measure(q[0],c[1])
circuit_drawer(qc)
```

## Fixed source (human gold)

```python
from qiskit import *
from qiskit.visualization import circuit_drawer
#definitions
c = [ ClassicalRegister(1) for _ in range(2) ]
q = QuantumRegister(1)
qc = QuantumCircuit(q)
for register in c:
    qc.add_register( register )
    qc.h(q)
qc.measure(q,c[0])
qc.x(q[0]).c_if(c[0], 0)
qc.measure(q,c[1])
circuit_drawer(qc)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,12 +1,13 @@
 from qiskit import *
+from qiskit.visualization import circuit_drawer
 #definitions
+c = [ ClassicalRegister(1) for _ in range(2) ]
 q = QuantumRegister(1)
-c = ClassicalRegister(2)
-qc = QuantumCircuit(q,c)
-
-# building the circuit
-qc.h(q)
-qc.measure(q[0],c[0])
-qc.x(q[0]).c[0]_if(c[0], 0)
-qc.measure(q[0],c[1])
+qc = QuantumCircuit(q)
+for register in c:
+    qc.add_register( register )
+    qc.h(q)
+qc.measure(q,c[0])
+qc.x(q[0]).c_if(c[0], 0)
+qc.measure(q,c[1])
 circuit_drawer(qc)
```
