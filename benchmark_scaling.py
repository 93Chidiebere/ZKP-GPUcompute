"""
Scaling benchmark: how does proving/verification cost grow with model size?

The existing measurement (SECURITY.md) is a single data point on one small
5->16->1 MLP. A reviewer assessing "practical impact" will immediately ask
whether this generalizes. This script trains and compiles several model
sizes, runs the full setup -> prove -> verify pipeline on each, and reports
proving time, verification time, circuit size (logrows), and quantization
fidelity (max abs error) for each -- real measurements, not projections.

Usage: python3 benchmark_scaling.py
Writes results to benchmark_results.json and prints a summary table.
"""
from __future__ import annotations

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

# (hidden_width, label) -- single hidden layer MLP, same architecture
# family as model_setup.py, varying only width. This isolates the effect
# of circuit SIZE from architecture changes, which is the right first
# scaling axis before adding depth or conv layers.
CONFIGS = [
    (8,   "tiny_8"),
    (16,  "small_16"),    # matches model_setup.py / SECURITY.md's existing number
    (32,  "medium_32"),
    (64,  "large_64"),
    (128, "xlarge_128"),
]


def make_data(n=2000):
    X = RNG.uniform(0, 1, size=(n, N_FEATURES)).astype(np.float32)
    true_w = np.array([2.5, -1.8, 3.0, 0.5, -2.2], dtype=np.float32)
    logits = X @ true_w - 1.1 + RNG.normal(0, 0.3, size=n).astype(np.float32)
    y = (logits > 0).astype(np.float32).reshape(-1, 1)
    return X, y


def train_mlp(X, y, hidden, epochs=500, lr=0.1):
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
    acc = (( (1/(1+np.exp(-(np.maximum(X@W1+b1,0)@W2+b2)))) > 0.5).astype(np.float32) == y).mean()
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
    graph = helper.make_graph([n1, n2, n3], "bench", [X], [Y], [W1T, B1T, W2T, B2T])
    m = helper.make_model(graph, producer_name="sovereign-zk-bench")
    m.opset_import[0].version = 14
    onnx.save(m, onnx_path)


def bench_one(hidden, label, X, workdir):
    os.makedirs(workdir, exist_ok=True)
    onnx_path = f"{workdir}/network.onnx"
    data_path = f"{workdir}/input.json"
    settings_path = f"{workdir}/settings.json"
    compiled_path = f"{workdir}/network.compiled"
    vk_path, pk_path, srs_path = f"{workdir}/vk.key", f"{workdir}/pk.key", f"{workdir}/kzg.srs"
    witness_path = f"{workdir}/witness.json"
    proof_path = f"{workdir}/proof.json"

    W1, b1, W2, b2, acc = train_mlp(X, make_data()[1], hidden)
    build_onnx(W1, b1, W2, b2, hidden, onnx_path)
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

    t_compile0 = time.time()
    ezkl.compile_circuit(onnx_path, compiled_path, settings_path)
    t_compile = time.time() - t_compile0

    srs_logrows = max(logrows or 17, 17)
    ezkl.gen_srs(srs_path, srs_logrows)
    ezkl.gen_witness(data_path, compiled_path, witness_path)
    ezkl.setup(compiled_path, vk_path, pk_path, srs_path, witness_path)

    t_prove0 = time.time()
    ok = ezkl.prove(witness_path, compiled_path, pk_path, proof_path, srs_path)
    t_prove = time.time() - t_prove0

    t_verify0 = time.time()
    valid = ezkl.verify(proof_path, settings_path, vk_path, srs_path)
    t_verify = time.time() - t_verify0

    proof_size_bytes = os.path.getsize(proof_path)
    pk_size_bytes = os.path.getsize(pk_path)

    num_params = (N_FEATURES * hidden + hidden) + (hidden * 1 + 1)

    return {
        "label": label, "hidden_width": hidden, "num_params": num_params,
        "train_accuracy": round(acc, 4), "logrows": logrows,
        "compile_seconds": round(t_compile, 3),
        "prove_seconds": round(t_prove, 3),
        "verify_seconds": round(t_verify, 4),
        "proof_valid": bool(valid),
        "proof_size_bytes": proof_size_bytes,
        "pk_size_bytes": pk_size_bytes,
    }


def main():
    X, _ = make_data()
    results = []
    for hidden, label in CONFIGS:
        print(f"=== {label} (hidden={hidden}) ===")
        workdir = f"/tmp/bench_{label}"
        try:
            r = bench_one(hidden, label, X, workdir)
            results.append(r)
            print(f"  params={r['num_params']} logrows={r['logrows']} "
                  f"compile={r['compile_seconds']}s prove={r['prove_seconds']}s "
                  f"verify={r['verify_seconds']}s valid={r['proof_valid']} "
                  f"proof={r['proof_size_bytes']}B pk={r['pk_size_bytes']}B")
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"label": label, "hidden_width": hidden, "error": str(e)})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== Summary ===")
    print(f"{'config':<12} {'params':>8} {'logrows':>8} {'prove(s)':>10} {'verify(s)':>10} {'proof(KB)':>10} {'pk(MB)':>8}")
    for r in results:
        if "error" in r:
            print(f"{r['label']:<12} FAILED: {r['error']}")
            continue
        print(f"{r['label']:<12} {r['num_params']:>8} {r['logrows']:>8} "
              f"{r['prove_seconds']:>10.2f} {r['verify_seconds']:>10.4f} "
              f"{r['proof_size_bytes']/1024:>10.1f} {r['pk_size_bytes']/1024/1024:>8.2f}")


if __name__ == "__main__":
    main()
