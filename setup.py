from setuptools import setup, find_packages

dependencies = [
    'swsssdk>=1.3.0',
    'enum34>=1.1.6',
]

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
    packages=find_packages('src'),
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
    classifiers=[
        'Intended Audience :: Developers',
        'Operating System :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ],
)
