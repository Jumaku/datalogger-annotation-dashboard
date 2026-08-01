import os
from os import path

# 1. Get the absolute path of the directory where THIS script lives
# BASE_DIR = os.path.abspath(os.path.join(os.getcwd(), os.pardir))

BASE_DIR = "/home/juk/freeze/"
# 2. Define your dictionary using paths relative to the script directory
APP_DIR = {
    "base": BASE_DIR,
    "data": path.join( BASE_DIR , "data", 'data_raw'),
    "procdata": path.join( BASE_DIR , "data", 'data_processed'),
    "scripts": path.join( BASE_DIR , "scripts"),
    "output": path.join( BASE_DIR , "output") 
}
