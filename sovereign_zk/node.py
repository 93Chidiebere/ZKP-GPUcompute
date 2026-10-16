import os
import json
import time
import warnings

from flask import Flask, request, jsonify
from cryptography.fernet import Fernet

os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")
import ezkl

app = Flask(__name__)
ALLOW_INSECURE_DEMO = os.environ.get("SOVEREIGN_ZK_ALLOW_INSECURE_DEMO") == "1"


@app.route("/compute", methods=["POST"])
def compute_proof():
    if not ALLOW_INSECURE_DEMO:
        return jsonify({
            "error": "Remote compute is disabled. This node is a non-attested "
                     "demo and must not receive sensitive data."
        }), 503

    warnings.warn(
        "INSECURE DEMO: this process receives the Fernet key and reads plaintext. "
        "Use synthetic data only.",
        RuntimeWarning,
        stacklevel=2,
    )
    print("--- [DEMO NODE] New synthetic-data compute job received ---")

    if "encrypted_data" not in request.files:
        return jsonify({"error": "Missing encrypted_data"}), 400
    if "compiled_model" not in request.files:
        return jsonify({"error": "Missing compiled_model"}), 400
    if "pk_key" not in request.files or "kzg_srs" not in request.files:
        return jsonify({"error": "Missing proving key or SRS"}), 400

    fernet_key = request.headers.get("fernet-key")
    if not fernet_key:
        return jsonify({"error": "Missing fernet-key header"}), 400

    try:
        cipher_suite = Fernet(fernet_key.encode("utf-8"))
        encrypted_bytes = request.files["encrypted_data"].read()
        plaintext = cipher_suite.decrypt(encrypted_bytes)
        data_dict = json.loads(plaintext.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Demo payload decryption failed"}), 400

    # The demo writes only into the process working directory. This is not
    # secure enclave storage and must not be used for personal data.
    data_path = "temp_encrypted.bin"
    model_path = "temp_network.compiled"
    pk_path = "temp_pk.key"
    srs_path = "temp_kzg.srs"
    enclave_input_path = "temp_enclave_input.json"
    witness_path = "temp_witness.json"
    output_proof_path = "temp_proof.json"

    request.files["encrypted_data"].save(data_path)
    request.files["compiled_model"].save(model_path)
    request.files["pk_key"].save(pk_path)
    request.files["kzg_srs"].save(srs_path)

    with open(enclave_input_path, "w", encoding="utf-8") as output:
        json.dump(data_dict, output)

    try:
        ezkl.gen_witness(enclave_input_path, model_path, witness_path)
        start_prove = time.time()
        result = ezkl.prove(
            witness_path, model_path, pk_path, output_proof_path, "single", srs_path
        )
        elapsed = time.time() - start_prove
        if not result:
            return jsonify({"error": "Failed to generate proof"}), 500

        with open(output_proof_path, "r", encoding="utf-8") as proof_file:
            proof_data = json.load(proof_file)
        print(f"[+] Per-job EZKL proof generated in {elapsed:.2f}s.")
        return jsonify(proof_data)
    finally:
        for path in (
            data_path,
            model_path,
            pk_path,
            srs_path,
            enclave_input_path,
            witness_path,
            output_proof_path,
        ):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


def run_node(port=8000):
    if ALLOW_INSECURE_DEMO:
        warnings.warn(
            "SOVEREIGN_ZK_ALLOW_INSECURE_DEMO=1: node can see plaintext; "
            "do not expose it or use real personal data.",
            RuntimeWarning,
            stacklevel=2,
        )
    print(f"[*] Sovereign-ZK demo node running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run_node()
