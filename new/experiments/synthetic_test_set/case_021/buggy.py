from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)
qc.id(0)
backend = Aer.get_backend('qasm_simulator')
job = backend.run(qc)
counts = job.result().get_counts(qc)
print(counts)
