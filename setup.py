# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
import re, ast

# get version from __version__ variable in ibtevolve/__init__.py
_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('ibtevolve/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))
with open("requirements.txt") as f:
	requirements = f.read().strip().split("\n")

setup(
	name='ibtevolve',
	version=version,
	description='Ibtevolve',
	author='FinByz Tech',
	author_email='info@finbyz.com',
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=requirements,
	dependency_links=[str(ir._link) for ir in requirements if ir._link]
)
