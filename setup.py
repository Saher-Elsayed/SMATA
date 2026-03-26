from setuptools import setup, find_packages

setup(
    name="smata",
    version="2.0.0",
    author="Saher Elsayed",
    author_email="selsayed@seas.upenn.edu",
    description="Structured Mobile Application Testing Architecture",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/Saher-Elsayed/SMATA",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "uiautomator2>=2.16.0",
        "adbutils>=1.2.0",
        "psutil>=5.9.0",
        "click>=8.1.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Testing",
        "Intended Audience :: Science/Research",
    ],
    entry_points={
        "console_scripts": [
            "smata=smata.cli:main",
        ],
    },
)
