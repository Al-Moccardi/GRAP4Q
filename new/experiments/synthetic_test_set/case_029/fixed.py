from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer

def build_circuit():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.id(0)
    qc.measure([0, 1], [0, 1])
    return qc

def run_and_count():
    qc = build_circuit()
    backend = Aer.get_backend('qasm_simulator')
    job = backend.run(qc)
    counts = job.result().get_counts(qc)
    return counts

if __name__ == '__main__':
    print(run_and_count())
