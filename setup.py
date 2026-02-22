from setuptools import setup, find_packages

setup(
    name="isnad",
    version="0.3.0",
    description="Cryptographic trust chains for AI agent reputation — reference implementation",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Gendolf",
    author_email="gendolf@agentmail.to",
    url="https://github.com/Danieliushka/isnad-ref-impl",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=["pynacl>=1.5.0", "requests>=2.28.0"],
    extras_require={"dev": ["pytest>=7.0", "flask>=2.0"]},
    entry_points={"console_scripts": ["isnad=isnad.cli:main"]},
    python_requires=">=3.9",
    license="CC0-1.0",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Security :: Cryptography",
        "Topic :: Software Development :: Libraries",
        "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
        "Programming Language :: Python :: 3",
    ],
    keywords="agent trust reputation cryptography provenance isnad",
)
