import sys

from setuptools import setup

PY3x = sys.version_info >= (3, 0)

dependencies = [
    'swsssdk>=1.3.0',
] + ([
] if PY3x else [
    'enum34>=1.1.6',
])

test_deps = [
    'mockredispy>=2.9.3',
]

high_performance_deps = [
    'swsssdk[high_perf]>=1.1',
]

setup(
    name='sonic-d',
    install_requires=dependencies,
    version='2.0.0',
    packages=[
        'src/sonic_syncd',
        'src/lldp_syncd',
        'tests',
    ],
    extras_require={
        'testing': test_deps,
        'high_perf': high_performance_deps,
    },
    license='Apache 2.0',
    author='SONiC Team',
    author_email='linuxnetdev@microsoft.com',
    maintainer='Tom Booth',
    maintainer_email='thomasbo@microsoft.com',
    package_dir={
        'sonic_syncd': 'src/sonic_syncd',
        'lldp_syncd': 'src/lldp_syncd',
    },
    package_data={
        'tests': [
            'mock_tables/*',
            'subproc_outputs/*',
            '*.py',
        ]
    },
    setup_requires= [
        'pytest-runner',
        'wheel',
    ],
    tests_require=[
        'pytest',
        'mock>=2.0.0',
        'mockredispy>=2.9.3',
    ],
    classifiers = [
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)
