from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
qc = QuantumCircuit(1, 1)
qc.h(0)
qc.iden(0)
qc.measure(0, 0)
backend = Aer.get_backend('qasm_simulator')
job = execute(qc, backend=backend)
counts = job.result().get_counts(qc)
print(counts)
