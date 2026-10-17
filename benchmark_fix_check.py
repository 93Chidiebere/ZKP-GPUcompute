"""
Confirms two bugs found in benchmark_scaling.py's first run and that the
fixes actually work, before trusting any corrected numbers:

  1. srs_logrows was computed as max(logrows or 17, 17), which equals 17
     whenever the circuit's own calibrated logrows is <= 17 -- i.e.
     ALWAYS in the first run (every config calibrated to logrows=15).
     Every proof paid for an unnecessarily large (2^17) trusted setup.
     Fix: srs_logrows = logrows if logrows is not None else 17 (no floor).

  2. train_mlp() was called as train_mlp(X, make_data()[1], hidden) --
     make_data() was called a SECOND time just to get its y, which is
     labels for a DIFFERENT random X than the one actually passed in.
     Train accuracy was ~51-56% (near chance) across every config as a
     direct result. Fix: generate (X, y) once, pass both consistently.

This script re-runs ONLY the small_16 config (matching the existing
SECURITY.md baseline) with both fixes, to get a clean before/after
comparison rather than assert the fix works without checking.
"""
import json
import os
import shutil
import time

import numpy as np
import onnx
from onnx import helper, TensorProto

os.environ.setdefault("HOME", os.environ.get("USERPROFILE", "/tmp"))
import ezkl

RNG = np.random.default_rng(42)
N_FEATURES = 5
HIDDEN = 16


def make_data(n=2000):
    X = RNG.uniform(0, 1, size=(n, N_FEATURES)).astype(np.float32)
    true_w = np.array([2.5, -1.8, 3.0, 0.5, -2.2], dtype=np.float32)
    logits = X @ true_w - 1.1 + RNG.normal(0, 0.3, size=n).astype(np.float32)
    y = (logits > 0).astype(np.float32).reshape(-1, 1)
    return X, y


def train_mlp(X, y, hidden, epochs=800, lr=0.1):
    n_in = X.shape[1]
    W1 = RNG.normal(0, 0.5, size=(n_in, hidden)).astype(np.float32)
    b1 = np.zeros((hidden,), dtype=np.float32)
    W2 = RNG.normal(0, 0.5, size=(hidden, 1)).astype(np.float32)
    b2 = np.zeros((1,), dtype=np.float32)
    n = X.shape[0]
    for _ in range(epochs):
        z1 = X @ W1 + b1
        a1 = np.maximum(z1, 0)
        z2 = a1 @ W2 + b2
        p = 1 / (1 + np.exp(-z2))
        dz2 = (p - y) / n
        dW2 = a1.T @ dz2; db2 = dz2.sum(axis=0)
        da1 = dz2 @ W2.T
        dz1 = da1 * (z1 > 0)
        dW1 = X.T @ dz1; db1 = dz1.sum(axis=0)
        W1 -= lr * dW1; b1 -= lr * db1
        W2 -= lr * dW2; b2 -= lr * db2
    p_final = 1/(1+np.exp(-(np.maximum(X@W1+b1,0)@W2+b2)))
    acc = ((p_final > 0.5).astype(np.float32) == y).mean()
    return W1, b1, W2, b2, float(acc)


def build_onnx(W1, b1, W2, b2, hidden, onnx_path):
    X = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, N_FEATURES])
    Y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1])
    W1T = helper.make_tensor("W1", TensorProto.FLOAT, [hidden, N_FEATURES], W1.T.flatten().tolist())
    B1T = helper.make_tensor("B1", TensorProto.FLOAT, [hidden], b1.flatten().tolist())
    W2T = helper.make_tensor("W2", TensorProto.FLOAT, [1, hidden], W2.T.flatten().tolist())
    B2T = helper.make_tensor("B2", TensorProto.FLOAT, [1], b2.flatten().tolist())
    n1 = helper.make_node("Gemm", ["input", "W1", "B1"], ["fc1_out"], transB=1)
    n2 = helper.make_node("Relu", ["fc1_out"], ["relu_out"])
    n3 = helper.make_node("Gemm", ["relu_out", "W2", "B2"], ["output"], transB=1)
    graph = helper.make_graph([n1, n2, n3], "bench_fixed", [X], [Y], [W1T, B1T, W2T, B2T])
    m = helper.make_model(graph, producer_name="sovereign-zk-bench-fixed")
    m.opset_import[0].version = 14
    onnx.save(m, onnx_path)


def main():
    X, y = make_data()  # generated ONCE, passed consistently -- bug 2 fix

    workdir = "/tmp/bench_fix_check"
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)
    onnx_path = f"{workdir}/network.onnx"
    data_path = f"{workdir}/input.json"
    settings_path = f"{workdir}/settings.json"
    compiled_path = f"{workdir}/network.compiled"
    vk_path, pk_path, srs_path = f"{workdir}/vk.key", f"{workdir}/pk.key", f"{workdir}/kzg.srs"
    witness_path = f"{workdir}/witness.json"
    proof_path = f"{workdir}/proof.json"

    W1, b1, W2, b2, acc = train_mlp(X, y, HIDDEN)
    print(f"train_accuracy (fixed) = {acc:.4f}   (buggy run reported 0.535)")
    build_onnx(W1, b1, W2, b2, HIDDEN, onnx_path)
    with open(data_path, "w") as f:
        json.dump({"input_data": X[0:1].tolist()}, f)

    py_run_args = ezkl.PyRunArgs()
    py_run_args.input_visibility = "private"
    py_run_args.output_visibility = "public"
    py_run_args.param_visibility = "fixed"
    ezkl.gen_settings(onnx_path, settings_path, py_run_args=py_run_args)
    ezkl.calibrate_settings(data_path, onnx_path, settings_path, "resources")

    with open(settings_path) as f:
        settings = json.load(f)
    logrows = settings.get("run_args", {}).get("logrows")
    print(f"circuit's own calibrated logrows = {logrows}")

    srs_logrows = logrows if logrows is not None else 17  # bug 1 fix: no floor
    print(f"SRS degree used (fixed) = {srs_logrows}   (buggy run always used 17)")

    ezkl.compile_circuit(onnx_path, compiled_path, settings_path)
    ezkl.gen_srs(srs_path, srs_logrows)
    ezkl.gen_witness(data_path, compiled_path, witness_path)
    ezkl.setup(compiled_path, vk_path, pk_path, srs_path, witness_path)

    t0 = time.time()
    ezkl.prove(witness_path, compiled_path, pk_path, proof_path, srs_path)
    t_prove = time.time() - t0

    t0 = time.time()
    valid = ezkl.verify(proof_path, settings_path, vk_path, srs_path)
    t_verify = time.time() - t0

    pk_size = os.path.getsize(pk_path)

    print(f"\n=== CORRECTED small_16 result ===")
    print(f"prove_seconds={t_prove:.2f}  (buggy run: 76.17s)")
    print(f"verify_seconds={t_verify:.4f}  (buggy run: 67.52s)")
    print(f"pk_size_bytes={pk_size}  (buggy run: 138479371)")
    print(f"proof_valid={valid}")

    with open("benchmark_fix_check_result.json", "w") as f:
        json.dump({
            "logrows": logrows, "srs_logrows_used": srs_logrows,
            "prove_seconds": round(t_prove, 3), "verify_seconds": round(t_verify, 4),
            "pk_size_bytes": pk_size, "proof_valid": bool(valid),
            "train_accuracy": round(acc, 4),
        }, f, indent=2)

    shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
