from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, execute
from qiskit_aer import Aer

def case_033_circuit(shots=1024):
    qr = QuantumRegister(2, 'q')
    cr = ClassicalRegister(2, 'c')
    qc = QuantumCircuit(qr, cr)
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    qc.id(0)
    qc.measure(qr, cr)
    backend = Aer.get_backend('qasm_simulator')
    job = execute(qc, backend=backend, shots=shots)
    return job.result().get_counts(qc)

if __name__ == '__main__':
    print(case_033_circuit())
