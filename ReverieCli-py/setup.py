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
    url="https://github.com/Lin-Silver/Reverie-Cli",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "reverie": [
            "builtin_skills/*/SKILL.md",
            "builtin_skills/*/agents/*.yaml",
            "builtin_skills/*/references/*.md",
            "engine/vendor/live2d/*.js",
            "computer_use/*.md",
        ],
        "reverie.agent": ["tool_manifest.json"],
    },
    python_requires=">=3.10",
    install_requires=[
        # CLI and Display
        "rich==15.0.0",
        "click==8.4.2",
        "tqdm==4.68.3",
        "prompt-toolkit==3.0.52",
        "pathspec==1.1.1",
        
        # HTTP and API
        "requests==2.34.2",
        "httpx==0.28.1",
        "openai==2.44.0",
        "anthropic==0.112.0",

        # Git integration
        "GitPython==3.1.50",
        
        # Web search
        "ddgs==9.14.4",
        "beautifulsoup4==4.15.0",
        "playwright==1.61.0",

        # Runtime support used by story/game/token tooling
        "PyYAML==6.0.3",
        "tiktoken==0.13.0",
        "Pillow==12.2.0",
        "jsonschema==4.26.0",
        "uiautomation==2.0.29; platform_system == 'Windows'",

        # Reverie Engine runtime
        "pyglet==2.1.15",
        "moderngl==5.12.0",
        "glcontext==3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest==9.1.1",
            "pytest-cov==7.0.0",
            "black==26.3.1",
            "mypy==1.19.1",
        ],
        "treesitter": [
            "tree-sitter==0.26.0",
            "tree-sitter-python==0.25.0",
            "tree-sitter-javascript==0.25.0",
            "tree-sitter-typescript==0.23.2",
            "tree-sitter-c==0.24.2",
            "tree-sitter-cpp==0.23.4",
            "tree-sitter-rust==0.24.2",
            "tree-sitter-go==0.25.0",
            "tree-sitter-java==0.23.5",
            "tree-sitter-c-sharp==0.23.5",
            "tree-sitter-html==0.23.2",
            "tree-sitter-css==0.23.2",
        ],
        "build": [
            "pyinstaller==6.21.0",
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
