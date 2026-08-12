from setuptools import setup, find_packages

setup(
    name="neurosentinel",
    version="1.0.0",
    description="AI Security for Multi-Agent LLM Pipelines",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Ravindran M",
    author_email="ravindran07@example.com",
    url="https://neuro-sentinel-0nhi.onrender.com",
    py_modules=["neurosentinel_sdk"],
    install_requires=["requests>=2.31.0"],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Security",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)