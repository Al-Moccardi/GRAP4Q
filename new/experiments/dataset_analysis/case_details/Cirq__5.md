# Case `Cirq/5`

- **Split**: train
- **Group**: Cirq
- **Buggy lines**: 12  |  **Fixed lines**: 17
- **Lines changed** (del/add/mod): 0 / 9 / 8
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.5

## QChecker static analysis

No findings.

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 0
- Rules fired: `(none)`

## Buggy source

```python
import cirq
qubit = cirq.NamedQubit("myqubit")
circuit = cirq.Circuit(cirq.H(qubit))
for i in range(10):
    result2 = cirq.measure(qubit, key='myqubit')
    print(result2)
print(circuit)
# run simulation
result = cirq.Simulator().simulate(circuit)
print("result:")
print(result)
print(result2)
```

## Fixed source (human gold)

```python
import cirq
qubit = cirq.NamedQubit("myqubit")
circuit = cirq.Circuit()
circuit = cirq.Circuit(cirq.H(qubit))
circuit.append(cirq.measure(qubit, key='result'))
print(circuit)
s=cirq.Simulator()
samples=s.run(circuit, repetitions=1000)
print('Single measurement result:' ,samples.histogram(key='result'))

print('****************************************')
circuit2 = cirq.Circuit(cirq.H(qubit))
for i in range(10):
    circuit2.append(cirq.measure(qubit, key='myqubit'))
print(circuit2)
samples2 = s.run(circuit, repetitions=1000)
print('Hadamard follows by 10 measurements result:' ,samples2.histogram(key='result'))
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -1,12 +1,17 @@
 import cirq
 qubit = cirq.NamedQubit("myqubit")
+circuit = cirq.Circuit()
 circuit = cirq.Circuit(cirq.H(qubit))
+circuit.append(cirq.measure(qubit, key='result'))
+print(circuit)
+s=cirq.Simulator()
+samples=s.run(circuit, repetitions=1000)
+print('Single measurement result:' ,samples.histogram(key='result'))
+
+print('****************************************')
+circuit2 = cirq.Circuit(cirq.H(qubit))
 for i in range(10):
-    result2 = cirq.measure(qubit, key='myqubit')
-    print(result2)
-print(circuit)
-# run simulation
-result = cirq.Simulator().simulate(circuit)
-print("result:")
-print(result)
-print(result2)
+    circuit2.append(cirq.measure(qubit, key='myqubit'))
+print(circuit2)
+samples2 = s.run(circuit, repetitions=1000)
+print('Hadamard follows by 10 measurements result:' ,samples2.histogram(key='result'))
```
