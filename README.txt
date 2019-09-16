Autodownloader README
=====================
Version 0.2

Robbert Gorter
Maurice van de Klundert
Mark de Vries
Hans de Goede <j.w.r.degoede@hhs.nl>

Autodownloader is a program written in Python that can be used to automatically
download files that are not freely distributable. The program can choose from
multiple mirrors and download the files to a specified location. The files
will also be checked using an md5 checksum.


USAGE
-----

To use Autodownloader the packager has to make a new configuration file. In
this file messages regarding internet access and the user license can be
configures as well as the list of files and mirrors.

The program can be started from the commandline like this:
./AutoDL.py <autodl-configuration-file>
Then it will first show all configured messages for to the user and when the
user accepts these messages, then downloads the files. 

An example config file is included, the easiest way to create a new
configfile is to use the example file and modify it to the wishes of the
packager. This way Autodownloader will have the correct information to run the
download-process properly.


LICENSE
-------

The GPL licence applies to this software. Please read the included COPYING file
for detailed information.
