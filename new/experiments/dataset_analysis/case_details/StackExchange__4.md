# Case `StackExchange/4`

- **Split**: train
- **Group**: StackExchange
- **Buggy lines**: 59  |  **Fixed lines**: 65
- **Lines changed** (del/add/mod): 0 / 18 / 14
- **API drift**: 0.0  |  **Identifier Jaccard**: 0.9385

## QChecker static analysis

1 finding(s); rules fired: `QC04`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 2
- Rules fired: `R1,R6`

## Buggy source

```python
from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit, Aer, execute

# Initialize circuit
m_qubit = QuantumRegister(1)
search_register = QuantumRegister(4)
result_register = ClassicalRegister(4)
ancillaries = QuantumRegister(3)
circuit = QuantumCircuit(search_register, result_register, m_qubit, ancillaries)

# Put M qubit into 1-superposition
circuit.x(m_qubit)
circuit.h(m_qubit)

# Put search qubits into superposition
circuit.h(search_register)

for _ in range(2):

    # Encode S1 * !S2 * S3
    circuit.x( search_register[2] )
    circuit.ccx( search_register[1], search_register[2], ancillaries[0] )
    circuit.ccx( search_register[3], ancillaries[0], ancillaries[1] )
    circuit.x( search_register[2] )

    # Encode S0 * S1
    circuit.ccx( search_register[0], search_register[1], ancillaries[2] )

    # Encode oracle ((S0 * S1) + (S1 * !S2 * S3))
    circuit.x(ancillaries)
    circuit.ccx( ancillaries[1], ancillaries[2], m_qubit[0] )
    circuit.x(ancillaries)
    circuit.x(m_qubit)

    # Reset ancillaries to be used later
    circuit.reset(ancillaries)

    # Do rotation about the average
    circuit.h(search_register)
    circuit.x(search_register)
    circuit.ccx( search_register[0], search_register[1], ancillaries[0] )
    circuit.ccx( search_register[2], ancillaries[0], ancillaries[1] )
    circuit.ccx( search_register[3], ancillaries[1], m_qubit[0] )
    circuit.x(search_register)
    circuit.x(m_qubit)
    circuit.h(search_register)

    # Reset ancillaries for use later
    circuit.reset(ancillaries)

circuit.measure(search_register, result_register)

# Run the circuit with a given number of shots
backend_sim = Aer.get_backend('qasm_simulator')
job_sim = execute(circuit, backend_sim, shots = 1024)
result_sim = job_sim.result()

# get_counts returns a dictionary with the bit-strings as keys
# and the number of times the string resulted as the value
print(result_sim.get_counts(circuit))
```

## Fixed source (human gold)

```python
from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit, Aer, execute

# Initialize circuit
m_qubit = QuantumRegister(1)
search_register = QuantumRegister(4)
result_register = ClassicalRegister(4)
ancillaries = QuantumRegister(3)
circuit = QuantumCircuit(search_register, result_register, m_qubit, ancillaries)

# Put M qubit into 1-superposition
circuit.x(m_qubit)
circuit.h(m_qubit)

# Put search qubits into superposition
circuit.h(search_register)

for _ in range(2):

    # Encode S1 * !S2 * S3
    circuit.x( search_register[2] )
    circuit.ccx( search_register[1], search_register[2], ancillaries[0] )
    circuit.ccx( search_register[3], ancillaries[0], ancillaries[1] )

# Encode S0 * S1
    circuit.ccx( search_register[0], search_register[1], ancillaries[2] )

# Encode oracle ((S0 * S1) + (S1 * !S2 * S3))
    circuit.x(ancillaries)
    circuit.ccx( ancillaries[1], ancillaries[2], m_qubit[0] )
    circuit.x(m_qubit)

# Return ancillaries to 0s so they can be used later
    circuit.x(ancillaries)
    circuit.ccx( search_register[0], search_register[1], ancillaries[2] )
    circuit.ccx( search_register[3], ancillaries[0], ancillaries[1] )
    circuit.ccx( search_register[1], search_register[2], ancillaries[0] )
    circuit.x( search_register[2] )

# Do rotation about the average
    circuit.h(search_register)
    circuit.x(search_register)
    circuit.ccx( search_register[0], search_register[1], ancillaries[0] )
    circuit.ccx( search_register[2], ancillaries[0], ancillaries[1] )
    circuit.ccx( search_register[3], ancillaries[1], m_qubit[0] )
    circuit.x(search_register)
    circuit.x(m_qubit)

# Return ancillaries to 0s for use later
    circuit.ccx( search_register[2], ancillaries[0], ancillaries[1] )
    circuit.ccx( search_register[0], search_register[1], ancillaries[0] )
    circuit.h(search_register)

# Reset ancillaries for use later
    circuit.reset(ancillaries)

circuit.measure(search_register, result_register)

# Run the circuit with a given number of shots
backend_sim = Aer.get_backend('qasm_simulator')
job_sim = execute(circuit, backend_sim, shots = 1024)
result_sim = job_sim.result()

# get_counts returns a dictionary with the bit-strings as keys
# and the number of times the string resulted as the value
print(result_sim.get_counts(circuit))
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -21,19 +21,21 @@
     circuit.ccx( search_register[1], search_register[2], ancillaries[0] )
     circuit.ccx( search_register[3], ancillaries[0], ancillaries[1] )
+
+# Encode S0 * S1
+    circuit.ccx( search_register[0], search_register[1], ancillaries[2] )
+
+# Encode oracle ((S0 * S1) + (S1 * !S2 * S3))
+    circuit.x(ancillaries)
+    circuit.ccx( ancillaries[1], ancillaries[2], m_qubit[0] )
+    circuit.x(m_qubit)
+
+# Return ancillaries to 0s so they can be used later
+    circuit.x(ancillaries)
+    circuit.ccx( search_register[0], search_register[1], ancillaries[2] )
+    circuit.ccx( search_register[3], ancillaries[0], ancillaries[1] )
+    circuit.ccx( search_register[1], search_register[2], ancillaries[0] )
     circuit.x( search_register[2] )
 
-    # Encode S0 * S1
-    circuit.ccx( search_register[0], search_register[1], ancillaries[2] )
-
-    # Encode oracle ((S0 * S1) + (S1 * !S2 * S3))
-    circuit.x(ancillaries)
-    circuit.ccx( ancillaries[1], ancillaries[2], m_qubit[0] )
-    circuit.x(ancillaries)
-    circuit.x(m_qubit)
-
-    # Reset ancillaries to be used later
-    circuit.reset(ancillaries)
-
-    # Do rotation about the average
+# Do rotation about the average
     circuit.h(search_register)
     circuit.x(search_register)
@@ -43,7 +45,11 @@
     circuit.x(search_register)
     circuit.x(m_qubit)
+
+# Return ancillaries to 0s for use later
+    circuit.ccx( search_register[2], ancillaries[0], ancillaries[1] )
+    circuit.ccx( search_register[0], search_register[1], ancillaries[0] )
     circuit.h(search_register)
 
-    # Reset ancillaries for use later
+# Reset ancillaries for use later
     circuit.reset(ancillaries)
```
