"""Setup module for rcluster."""

from setuptools import setup
from os import path
from pypandoc import convert

from rcluster import __title__, __ver__

here = path.abspath(path.dirname(__file__))
long_description = convert(path.join(here, 'README.md'), 'rst')
long_description = long_description.replace("\r\n", "\n")

setup(
    name=__title__,
    version=__ver__,
    description='R clusters on AWS',
    long_description=long_description,
    url='https://github.com/ElizabethAB/rcluster',
    author='Elizabeth Byerly',
    author_email='elizabeth.byerly@gmail.com',
    license='MIT',
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Clustering",
        "Topic :: Scientific/Engineering",
        "Topic :: System :: Systems Administration"
    ],
    keywords='r aws cluster cloud',
    packages=['rcluster'],
    install_requires=['boto3', 'paramiko'],
    extras_require={'dev': ['coverage', 'pytest', 'pypandoc']},
    package_data={'rcluster': ['data/*']},
    entry_points={
        'console_scripts': [
            'rcluster-config=rcluster.__exec__:config',
            'rcluster=rcluster.__exec__:main',
            'rcluster-open=rcluster.__exec__:retrieveCluster',
            'rcluster-terminate=rcluster.__exec__:terminate'
        ]
    }
)
