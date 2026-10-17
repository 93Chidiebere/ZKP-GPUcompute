from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="sovereign-zk",
    version="0.4.0",
    author="Chidiebere",
    author_email="vincent.christopher.189736@unn.edu.ng",
    description=(
        "Protocol + reference implementation for commit-then-challenge ZK-audited "
        "cross-border inference. Prototype status: the included simulated backend "
        "provides NO hardware isolation -- see SECURITY.md before using with real "
        "sensitive data."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/93Chidiebere/ZKP-GPUcompute",
    packages=find_packages(include=["sovereign_zk", "sovereign_zk.*"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
    ],
    python_requires=">=3.8",
    install_requires=[
        # Pinned: ezkl>=23 changed prove()'s signature (dropped the
        # "proof_type" positional arg present in 22.x). The original
        # prototype's unpinned ">=22.3.0" would install a version whose
        # API it no longer calls correctly.
        "ezkl>=23.0.0,<24",
        "cryptography>=41.0.0",
        "requests>=2.31.0",
        "flask>=3.0.0",
        "numpy>=1.24.0",
        "onnx>=1.14.0",
    ],
)
