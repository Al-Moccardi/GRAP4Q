# Case `StackExchange/9`

- **Split**: train
- **Group**: StackExchange
- **Buggy lines**: 34  |  **Fixed lines**: 34
- **Lines changed** (del/add/mod): 0 / 0 / 1
- **API drift**: 0.0  |  **Identifier Jaccard**: 1.0

## QChecker static analysis

1 finding(s); rules fired: `QC04`

## Rule-based APR result

- Lines-F1 = **0.0** (P=0.0, R=0.0)
- Edits produced: 2
- Rules fired: `R1,R7`

## Buggy source

```python
from qiskit import(
  QuantumCircuit,
  execute,
  Aer)
from qiskit.visualization import plot_histogram

# Use Aer's qasm_simulator
simulator = Aer.get_backend('qasm_simulator')

# Create a Quantum Circuit acting on the q register
circuit = QuantumCircuit(3, 3)

# Add a X gate on qubit 0
circuit.x(0)

# Add a CX (CNOT) gate on control qubit 0 and target qubit 1
circuit.cx(0, 1)

circuit.barrier()
# Map the quantum measurement to the classical bits
circuit.measure([0,1,2], [0,1,2])

# Execute the circuit on the qasm simulator
job = execute(circuit, simulator, shots=1000)

# Grab results from the job
result = job.result()

# Returns counts
counts = result.get_counts(circuit)
print("\nTotal count:",counts)

# Draw the circuit
circuit.draw()
```

## Fixed source (human gold)

```python
from qiskit import(
  QuantumCircuit,
  execute,
  Aer)
from qiskit.visualization import plot_histogram

# Use Aer's qasm_simulator
simulator = Aer.get_backend('qasm_simulator')

# Create a Quantum Circuit acting on the q register
circuit = QuantumCircuit(3, 3)

# Add a X gate on qubit 0
circuit.x(0)

# Add a CX (CNOT) gate on control qubit 0 and target qubit 1
circuit.cx(0, 1)

circuit.barrier()
# Map the quantum measurement to the classical bits
circuit.measure([0,1,2], [2,1,0])

# Execute the circuit on the qasm simulator
job = execute(circuit, simulator, shots=1000)

# Grab results from the job
result = job.result()

# Returns counts
counts = result.get_counts(circuit)
print("\nTotal count:",counts)

# Draw the circuit
circuit.draw()
```

## Unified diff

```diff
--- buggy.py
+++ fixed.py
@@ -19,5 +19,5 @@
 circuit.barrier()
 # Map the quantum measurement to the classical bits
-circuit.measure([0,1,2], [0,1,2])
+circuit.measure([0,1,2], [2,1,0])
 
 # Execute the circuit on the qasm simulator
```
