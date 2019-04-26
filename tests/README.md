# How to run the tests
  Install the following packages
  ```
   sudo apt-get install python-setuptools
   sudo apt-get install python-pip
   sudo pip install pytest
   sudo pip install mockredispy
   sudo pip install mock
  ```
  Checkout sonic-py-swsssdk source
  ```
   git clone https://github.com/Azure/sonic-py-swsssdk.git
   cd sonic-py-swsssdk
   sudo python setup.py build
   sudo python setup.py install
  ```
  Run test
  ```
   cd sonic-dbsyncd/tests
   pytest -v
  ```