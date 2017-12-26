#!/usr/bin/env python

# Setuptools is a slightly nicer distribution utility that can create 'eggs'.
from setuptools import setup, find_packages

setup(name='xbrhx909_serial',
    version='0.9.0',
    description='Serial Control Protocol for Sony Television model XBR HX909 (and similar devices)',
    author='Kevin Williams',
    author_email='kevin@weblivion.com',
    url='http://www.weblivion.com/',
    package_dir={'':'src'},
    packages=find_packages('src'),
    include_package_data=True,
    install_requires=['pyserial'],
    zip_safe=False,
)


