from qiskit import QuantumCircuit, execute
from qiskit_aer import Aer

def case_056_circuit():
    qc = QuantumCircuit(4, 4)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.cx(2, 3)
    qc.id(0)
    qc.measure([0, 1, 2, 3], [0, 1, 2, 3])
    backend = Aer.get_backend('local_qasm_simulator')
    job = execute(qc, backend=backend, shots=2048)
    return job.result().get_counts(qc)

if __name__ == '__main__':
    print(case_056_circuit())
