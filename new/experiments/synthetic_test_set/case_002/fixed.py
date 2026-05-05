from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, execute
from qiskit_aer import Aer
qr = QuantumRegister(2)
cr = ClassicalRegister(2)
qc = QuantumCircuit(qr, cr)
qc.h(qr[0])
qc.cx(qr[0], qr[1])
qc.id(qr[0])
qc.measure(qr, cr)
backend = Aer.get_backend('qasm_simulator')
job = backend.run(qc)
counts = job.result().get_counts(qc)
print(counts)
