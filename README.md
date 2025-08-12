Ouranos
=======

Ouranos is the companion application of [Gaia](https://github.com/vaamb/gaia.git).
It can be used to manage multiple instances of Gaia, log data and it provides a
web api to retrieve data.

Note
----

Ouranos is still in development and might not work properly.

Installation
------------

Ouranos is written in Python (v. >= 3.11) and requires some extra dependencies,
some that might not be shipped with Python.

Make sure you have them before trying to install Ouranos.

To do so on a Raspberry Pi, use

``apt update; apt install python3 python3-pip python3-venv git rustc`` (or 
``sudo apt update; sudo apt install python3 python3-pip python3-venv git rustc`` 
if required).

To install Ouranos, copy the `install.sh` script from the `scripts` directory and 
run it in the directory in which you want to install Ouranos
