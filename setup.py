import setuptools

REQUIRES = [
    'PyQt5',
    'psutil',
    'Av1an',
]

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="qencoder",
    version="2.1.4",
    author="Eli Stone",
    author_email="eli.stonium@gmail.com",
    description="Qt graphical interface for encoding",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/natis1/qencoder",
    packages=setuptools.find_packages('.', exclude='tests'),
    install_requires=REQUIRES,
    py_modules=['qenc', 'qencoder/mainwindow', 'qencoder/window', 'qencoder/av1anworkarounds'],
    entry_points={"console_scripts": ["qencoder=qenc:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
