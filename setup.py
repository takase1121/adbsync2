from setuptools import setup, find_packages

setup(
    name='adbsync2',
    version='0.1.0',
    entry_points={
        'console_scripts': ['adbsync2=cli:main']
    },
    install_requires=['tqdm~=4.48.2'],
    packages=find_packages()
)