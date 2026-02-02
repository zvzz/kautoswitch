from setuptools import setup, find_packages

setup(
    name="kautoswitch",
    version="0.1.0-4",
    description="KAutoSwitch for Ubuntu KDE — local-only keyboard layout corrector",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        # When installing via pip (dev), use these.
        # When installed via .deb, these are satisfied by Debian deps.
    ],
    entry_points={
        "console_scripts": [
            "kautoswitch=kautoswitch.main:main",
        ],
    },
    package_data={
        "kautoswitch": [
            "resources/*",
            "vendor/spellchecker/*.py",
            "vendor/spellchecker/resources/*.gz",
            "vendor/spellchecker/LICENSE",
        ],
    },
    include_package_data=True,
)
