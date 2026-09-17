from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="sovereign-zk",
    version="0.1.0",
    author="Chidiebere",
    author_email="vincent.christopher.189736@unn.edu.ng",
    description="A lightweight, privacy-preserving framework for cross-border GPU compute using Zero-Knowledge Proofs.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/93Chidiebere/ZKP-GPUcompute",
    packages=find_packages(include=["sovereign_zk", "sovereign_zk.*"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "ezkl>=22.3.0",
        "cryptography>=41.0.0",
        "requests>=2.31.0",
        "flask>=3.0.0"
    ],
)
