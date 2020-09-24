import os
from os import path
from io import open
from setuptools import setup
from appdirs import user_config_dir


for fname in ["global_config.json"]:
    cfg_path = user_config_dir("aws/config")
    cfg_file = path.join(user_config_dir("aws"), fname)
    if not os.path.isdir(cfg_path) and not os.path.isfile(cfg_file):
        os.makedirs(cfg_path)
        os.system("cp config/" + fname + " " + cfg_file)

here = path.abspath(path.dirname(__file__)) + '/'
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='quickspot',
    version='0.0.1',
    description="Deploying EC2 spot instances on AWS",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/rahl13ramesh/quickspot',
    author='Rahul Ramesh',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Topic :: System :: Networking',
        "License :: OSI Approved :: MIT License",
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    packages=["quickspot"],
    entry_points={'console_scripts': ['qs=quickspot.aw:main']},
    install_requires=["boto3==1.11.17",
                      "colorama==0.4.3",
                      "cursor==1.3.4",
                      "docopt==0.6.2",
                      "numpy==1.18.1",
                      "spinners==0.0.24",
                      "tabulate==0.8.7"],
    data_files=[(user_config_dir("aws"),
                ['config/global_config.json',
                 'config/config.json'])],
    package_data={'quickspot': ['config/*.json']}
)
