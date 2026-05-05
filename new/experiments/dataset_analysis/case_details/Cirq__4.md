# Case `Cirq/4`

- **Split**: train
- **Group**: Cirq
- **Buggy lines**: 9  |  **Fixed lines**: 9
- **Lines changed** (del/add/mod): 0 / 6 / 7
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.5556

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
import cirq

number =6
qubits = cirq.LineQubit.range(number) 
def n_party_GHZ_circuit(qubits)
      GHZ_circuit = cirq.Circuit(cirq.H(qubits[i]),
                           cirq.CNOT(qubits[i], qubits[j]))

GHZ = cirq.final_density_matrix(n_party_GHZ_circuit)
```

## Fixed source (human gold)

```python
import cirq
number = 6
qubits = cirq.LineQubit.range(number) 
GHZ_circuit = cirq.Circuit(cirq.H(qubits[0]))
for i in range(number-1):
    C = cirq.Circuit(cirq.CX(qubits[i], qubits[i+1] ) )
    GHZ_circuit = GHZ_circuit + C                     

print(GHZ_circuit)
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,9 +1,9 @@
 import cirq
+number = 6
+qubits = cirq.LineQubit.range(number) 
+GHZ_circuit = cirq.Circuit(cirq.H(qubits[0]))
+for i in range(number-1):
+    C = cirq.Circuit(cirq.CX(qubits[i], qubits[i+1] ) )
+    GHZ_circuit = GHZ_circuit + C                     
 
-number =6
-qubits = cirq.LineQubit.range(number) 
-def n_party_GHZ_circuit(qubits)
-      GHZ_circuit = cirq.Circuit(cirq.H(qubits[i]),
-                           cirq.CNOT(qubits[i], qubits[j]))
-
-GHZ = cirq.final_density_matrix(n_party_GHZ_circuit)
+print(GHZ_circuit)
```
