import setuptools

REQUIRES = [
    'scipy',
    'scenedetect[opencv,progress_bar]',
    'opencv-python',
    'psutil',
    'numpy',
    'PyQt5',
]

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="qencoder",
    version="1.1.3",
    author="Eli Stone",
    author_email="eli.stonium@gmail.com",
    description="All-in-one encode toolkit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/natis1/qencoder",
    packages=setuptools.find_packages('.', exclude='tests'),
    install_requires=REQUIRES,
    py_modules=['qencoder', 'mainwindow', 'pav1n'],
    entry_points={"console_scripts": ["qencoder=qencoder:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
