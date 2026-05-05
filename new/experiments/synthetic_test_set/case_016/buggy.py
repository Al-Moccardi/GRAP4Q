from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer
def run():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.iden(0)
    qc.measure([0, 1], [0, 1])
    backend = Aer.get_backend('qasm_simulator')
    job = backend.run(qc)
    counts = job.result().get_counts(qc)
    return counts
print(run())
