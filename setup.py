from setuptools import setup, find_packages

dependencies = [
]

test_deps = [
    'pytest',
    'mock>=2.0.0',
    'mockredispy>=2.9.3',
    'swsssdk>=1.3.0'
]

high_performance_deps = [
]

setup(
    name='sonic-d',
    install_requires=dependencies,
    version='2.0.0',
    tests_require=test_deps,
    packages=find_packages('src'),
    extras_require={
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
    setup_requires= [
        'pytest-runner',
        'wheel',
    ],
    classifiers = [
        'Intended Audience :: Developers',
        'Operating System :: Linux',
        'Programming Language :: Python :: 3.7',
    ],
)
