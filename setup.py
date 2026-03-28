"""
Reverie Cli - Setup Script

Install with: pip install -e .
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read canonical package version without importing the package.
about = {}
exec((Path(__file__).parent / "reverie" / "version.py").read_text(encoding="utf-8"), about)

# Read README if exists
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

setup(
    name="reverie-cli",
    version=about["__version__"],
    author="Raiden",
    author_email="raiden@reverie.dev",
    description="World-Class Context Engine Coding Assistant",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/raiden/reverie-cli",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "reverie.engine_lite": ["vendor/live2d/live2dcubismcore.min.js"],
    },
    python_requires=">=3.10",
    install_requires=[
        # CLI and Display
        "rich>=13.0.0",
        "click>=8.0.0",
        "tqdm>=4.65.0",
        
        # HTTP and API
        "requests>=2.31.0",
        "openai>=1.20.0",
        "anthropic>=0.40.0",

        # Git integration
        "GitPython>=3.1.0",
        
        # Web search
        "ddgs>=9.11.1",
        "beautifulsoup4>=4.12.0",

        # Runtime support used by story/game/token tooling
        "PyYAML>=6.0.0",
        "tiktoken>=0.5.0",
        "Pillow>=10.0.0",

        # Reverie Engine runtime
        "pyglet>=2.0.16",
        "moderngl>=5.10.0",
        "glcontext>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
        "treesitter": [
            "tree-sitter>=0.20.0",
            "tree-sitter-python>=0.20.0",
            "tree-sitter-javascript>=0.20.0",
            "tree-sitter-typescript>=0.20.0",
        ],
        "build": [
            "pyinstaller>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "reverie=reverie.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Software Development",
        "Topic :: Software Development :: Code Generators",
    ],
    keywords="ai, coding, assistant, context-engine, llm",
)
