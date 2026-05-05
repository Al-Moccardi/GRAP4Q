# Case `StackExchange/16`

- **Split**: val
- **Group**: StackExchange
- **Buggy lines**: 11  |  **Fixed lines**: 9
- **Lines changed** (del/add/mod): 0 / 3 / 8
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.6667

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
from qiskit import *

q = QuantumRegister(2)
subnode = QuantumRegister(2)
qc = QuantumCircuit(q,subnode)
qc.ccx(subnode[0], subnode[1], q[1])
if (q[1] ==1) : 
    qc.x(q[0])
qc.x(q[1]) 
qc.ccx(subnode[0], subnode[1], q[1])
qc.draw()
```

## Fixed source (human gold)

```python
from qiskit import *
q = QuantumRegister(5)
c = ClassicalRegister(5)
qc = QuantumCircuit(q,c)

qc.ccx(q[0],q[1],q[3])
qc.ccx(q[2],q[3],q[4])
qc.ccx(q[0],q[1],q[3])
qc.draw()
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,11 +1,9 @@
 from qiskit import *
+q = QuantumRegister(5)
+c = ClassicalRegister(5)
+qc = QuantumCircuit(q,c)
 
-q = QuantumRegister(2)
-subnode = QuantumRegister(2)
-qc = QuantumCircuit(q,subnode)
-qc.ccx(subnode[0], subnode[1], q[1])
-if (q[1] ==1) : 
-    qc.x(q[0])
-qc.x(q[1]) 
-qc.ccx(subnode[0], subnode[1], q[1])
+qc.ccx(q[0],q[1],q[3])
+qc.ccx(q[2],q[3],q[4])
+qc.ccx(q[0],q[1],q[3])
 qc.draw()
```
