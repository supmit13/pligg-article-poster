from distutils.core import setup
import py2exe
import os, sys

sys.path.append(os.getcwd() + os.path.sep + r"handlers")
sys.path.append(os.getcwd() + os.path.sep + r"api")
sys.path.append(r"C:\\Python25\\Lib\\site-packages")
sys.path.append(r"C:\\Python25\\Lib")
sys.path.append(os.getcwd() + os.path.sep + r"api" + os.path.sep + "xgoogle")

setup(console=['runManager.py'])
