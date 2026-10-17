"""
Setup phase: train a small model, then compile it into a ZK circuit.

Fix from the original prototype: every weight in the old network.onnx was
hardcoded to 0.0. That proves the circuit executes some arithmetic
correctly, but it does NOT demonstrate anything about verifying a real
model's inference -- a zero-weight network outputs the same thing (0) for
every input, challenged or not.

This version trains an actual (small, synthetic) fraud-score classifier
with plain NumPy gradient descent -- no torch dependency needed for a
5-feature logistic model -- so the compiled circuit has learned,
non-trivial weights. The synthetic data and task are illustrative, not a
real fraud dataset; swap `make_synthetic_fraud_data()` for a real training
pipeline before using this for anything beyond protocol testing.
"""

import json
import os

import numpy as np
import onnx
from onnx import helper, TensorProto

os.environ.setdefault("HOME", os.environ.get("USERPROFILE", "/tmp"))
import ezkl

RNG = np.random.default_rng(42)
N_FEATURES = 5
N_HIDDEN = 16


def make_synthetic_fraud_data(n=4000):
    """Toy separable-ish data: a weighted combination of 5 "transaction
    features" plus noise decides the fraud label. This is a stand-in for a
    real labeled dataset -- the point here is non-zero, non-trivial
    weights, not model quality."""
    X = RNG.uniform(0, 1, size=(n, N_FEATURES)).astype(np.float32)
    true_w = np.array([2.5, -1.8, 3.0, 0.5, -2.2], dtype=np.float32)
    logits = X @ true_w - 1.1 + RNG.normal(0, 0.3, size=n).astype(np.float32)
    y = (logits > 0).astype(np.float32).reshape(-1, 1)
    return X, y


def train_mlp(X, y, hidden=N_HIDDEN, epochs=800, lr=0.1):
    """Two-layer MLP (Linear -> ReLU -> Linear), trained with plain-NumPy
    gradient descent. Matches the Gemm->Relu->Gemm ONNX graph shape used
    below so the trained weights drop straight into the circuit."""
    n_in = X.shape[1]
    W1 = RNG.normal(0, 0.5, size=(n_in, hidden)).astype(np.float32)
    b1 = np.zeros((hidden,), dtype=np.float32)
    W2 = RNG.normal(0, 0.5, size=(hidden, 1)).astype(np.float32)
    b2 = np.zeros((1,), dtype=np.float32)

    n = X.shape[0]
    for epoch in range(epochs):
        z1 = X @ W1 + b1
        a1 = np.maximum(z1, 0)
        z2 = a1 @ W2 + b2
        p = 1 / (1 + np.exp(-z2))

        loss = -np.mean(y * np.log(p + 1e-7) + (1 - y) * np.log(1 - p + 1e-7))

        dz2 = (p - y) / n
        dW2 = a1.T @ dz2
        db2 = dz2.sum(axis=0)
        da1 = dz2 @ W2.T
        dz1 = da1 * (z1 > 0)
        dW1 = X.T @ dz1
        db1 = dz1.sum(axis=0)

        W1 -= lr * dW1; b1 -= lr * db1
        W2 -= lr * dW2; b2 -= lr * db2

        if epoch % 200 == 0 or epoch == epochs - 1:
            acc = ((p > 0.5).astype(np.float32) == y).mean()
            print(f"    epoch {epoch:4d}  loss={loss:.4f}  acc={acc:.3f}")

    return W1, b1, W2, b2


def build_onnx(W1, b1, W2, b2, onnx_path="network.onnx"):
    """Same Gemm->Relu->Gemm graph shape as the original prototype, but
    with the trained weights above instead of zeros. ezkl's quantized
    circuit will approximate a sigmoid-free logit output (ReLU + linear) --
    this mirrors the original architecture's choice to keep the final
    activation out of the circuit and apply it client-side if needed."""
    X = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, N_FEATURES])
    Y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1])

    W1T = helper.make_tensor("W1", TensorProto.FLOAT, [N_HIDDEN, N_FEATURES], W1.T.flatten().tolist())
    B1T = helper.make_tensor("B1", TensorProto.FLOAT, [N_HIDDEN], b1.flatten().tolist())
    W2T = helper.make_tensor("W2", TensorProto.FLOAT, [1, N_HIDDEN], W2.T.flatten().tolist())
    B2T = helper.make_tensor("B2", TensorProto.FLOAT, [1], b2.flatten().tolist())

    node1 = helper.make_node("Gemm", ["input", "W1", "B1"], ["fc1_out"], transB=1)
    node2 = helper.make_node("Relu", ["fc1_out"], ["relu_out"])
    node3 = helper.make_node("Gemm", ["relu_out", "W2", "B2"], ["output"], transB=1)

    graph = helper.make_graph([node1, node2, node3], "FraudDetection", [X], [Y], [W1T, B1T, W2T, B2T])
    onnx_model = helper.make_model(graph, producer_name="sovereign-zk")
    onnx_model.opset_import[0].version = 14
    onnx.save(onnx_model, onnx_path)
    return onnx_path


def setup():
    print("--- Sovereign-ZK Setup Phase ---")

    print("[*] Generating synthetic training data...")
    X, y = make_synthetic_fraud_data()

    print("[*] Training 5->16->1 MLP (plain NumPy gradient descent)...")
    W1, b1, W2, b2 = train_mlp(X, y)

    print("[*] Exporting trained model to ONNX...")
    onnx_path = build_onnx(W1, b1, W2, b2)
    print(f"[+] Model exported to {onnx_path} (non-zero, trained weights)")

    sample_input = X[0:1].tolist()
    data_path = "input.json"
    with open(data_path, "w") as f:
        json.dump({"input_data": sample_input}, f)
    print(f"[+] Calibration sample saved to {data_path}")

    settings_path = "settings.json"
    compiled_model_path = "network.compiled"
    vk_path, pk_path, srs_path = "vk.key", "pk.key", "kzg.srs"

    print("[*] Generating EZKL settings...")
    py_run_args = ezkl.PyRunArgs()
    py_run_args.input_visibility = "private"
    py_run_args.output_visibility = "public"
    py_run_args.param_visibility = "fixed"
    ezkl.gen_settings(onnx_path, settings_path, py_run_args=py_run_args)

    print("[*] Calibrating settings...")
    ezkl.calibrate_settings(data_path, onnx_path, settings_path, "resources")

    print("[*] Compiling ZK circuit...")
    ezkl.compile_circuit(onnx_path, compiled_model_path, settings_path)

    print("[*] Generating local SRS...")
    ezkl.gen_srs(srs_path, 17)

    print("[*] Generating setup witness...")
    witness_path = "witness.json"
    ezkl.gen_witness(data_path, compiled_model_path, witness_path)

    print("[*] Generating proving/verification keys...")
    ezkl.setup(compiled_model_path, vk_path, pk_path, srs_path, witness_path)

    from sovereign_zk.protocol.commitments import commit_model
    c_w = commit_model(compiled_model_path, vk_path)
    with open("model_commitment.json", "w") as f:
        json.dump({"c_w": c_w, "compiled_model": compiled_model_path, "vk": vk_path}, f, indent=2)

    print("--- Setup complete ---")
    print(f"C_W (model commitment, publish this when registering the node): {c_w}")
    print("Artifacts: network.compiled, pk.key (-> node), vk.key (kept by verifier).")


if __name__ == "__main__":
    setup()
