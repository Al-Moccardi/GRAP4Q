from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, execute
from qiskit_aer import Aer

def case_060_circuit(shots=1024):
    qr = QuantumRegister(2, 'q')
    cr = ClassicalRegister(2, 'c')
    qc = QuantumCircuit(qr, cr)
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    qc.id(0)
    qc.measure(qr, cr)
    backend = Aer.get_backend('local_qasm_simulator')
    job = backend.run(qc, shots=shots)
    return job.result().get_data(qc)

if __name__ == '__main__':
    print(case_060_circuit())
