from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
qc = QuantumCircuit(3, 3)
qc.h(0)
qc.cx(0, 1)
qc.cx(1, 2)
qc.iden(0)
qc.measure([0, 1, 2], [0, 1, 2])
backend = Aer.get_backend('qasm_simulator')
job = backend.run(qc)
counts = job.result().get_data(qc)
print(counts)
