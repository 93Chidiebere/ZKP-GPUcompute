import torch
import os
import json
import ezkl

# FIX: EZKL Rust bindings on Windows panic when trying to find the default repo path
# because 'HOME' is not a native Windows environment variable (it uses USERPROFILE).
os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")

# 1. Define a simple "Fraud Detection" Neural Network
import onnx
from onnx import helper, TensorProto

def setup():
    print("--- Starting Sovereign-ZK Setup Phase (Lagos, Nigeria) ---")
    
    # 1. Build a simple ONNX model directly to bypass PyTorch 2.14 Dynamo errors
    onnx_path = "network.onnx"
    
    # Inputs and Outputs
    X = helper.make_tensor_value_info('input', TensorProto.FLOAT, [1, 5])
    Y = helper.make_tensor_value_info('output', TensorProto.FLOAT, [1, 1])
    
    # Weights and Biases (Dummy values)
    W1 = helper.make_tensor('W1', TensorProto.FLOAT, [16, 5], [0.0]*80)
    B1 = helper.make_tensor('B1', TensorProto.FLOAT, [16], [0.0]*16)
    W2 = helper.make_tensor('W2', TensorProto.FLOAT, [1, 16], [0.0]*16)
    B2 = helper.make_tensor('B2', TensorProto.FLOAT, [1], [0.0])
    
    # Nodes (Linear -> ReLU -> Linear)
    node1 = helper.make_node('Gemm', ['input', 'W1', 'B1'], ['fc1_out'], transB=1)
    node2 = helper.make_node('Relu', ['fc1_out'], ['relu_out'])
    node3 = helper.make_node('Gemm', ['relu_out', 'W2', 'B2'], ['output'], transB=1)
    
    # Build Graph
    graph = helper.make_graph([node1, node2, node3], 'FraudDetection', [X], [Y], [W1, B1, W2, B2])
    onnx_model = helper.make_model(graph, producer_name='ezkl-fix')
    onnx_model.opset_import[0].version = 14
    
    # Save Model
    onnx.save(onnx_model, onnx_path)
    print(f"[+] Model exported manually to {onnx_path}")

    # Generate dummy input data for EZKL calibration
    data_path = "input.json"
    dummy_input = [[0.8, 0.1, 0.9, 0.2, 0.5]]
    data = {"input_data": dummy_input}
    with open(data_path, "w") as f:
        json.dump(data, f)
    print(f"[+] Dummy calibration data saved to {data_path}")

    # EZKL Configuration paths
    settings_path = "settings.json"
    compiled_model_path = "network.compiled"
    vk_path = "vk.key"
    pk_path = "pk.key"
    srs_path = "kzg.srs"

    print("[*] Generating EZKL settings...")
    # Generate settings with explicit args
    py_run_args = ezkl.PyRunArgs()
    py_run_args.input_visibility = "private"
    py_run_args.output_visibility = "public"
    py_run_args.param_visibility = "fixed"
    
    ezkl.gen_settings(onnx_path, settings_path, py_run_args=py_run_args)
    
    print("[*] Calibrating settings...")
    ezkl.calibrate_settings(data_path, onnx_path, settings_path, "resources")
    
    print("[*] Compiling ZK Circuit...")
    # Compile the circuit
    ezkl.compile_circuit(onnx_path, compiled_model_path, settings_path)
    
    print("[*] Generating local SRS (Structured Reference String)...")
    ezkl.gen_srs(srs_path, 17)
    
    print("[*] Generating dummy witness for setup...")
    witness_path = "witness.json"
    ezkl.gen_witness(data_path, compiled_model_path, witness_path)
    
    print("[*] Generating Proving and Verification Keys (Setup)...")
    ezkl.setup(compiled_model_path, vk_path, pk_path, srs_path, witness_path)
    
    print("--- Setup Complete ---")
    print("The Researcher now has:")
    print("1. network.compiled (The ZK Circuit to send to Kenya)")
    print("2. pk.key (The Prover Key to send to Kenya)")
    print("3. vk.key (The Verification Key kept safely in Nigeria)")

if __name__ == "__main__":
    setup()
