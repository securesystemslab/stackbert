import os
import json
from stacksyms import parseELF, checkLabels #, collectDisasLabels
from multiprocessing import Process, Pool, cpu_count
import argparse

parser = argparse.ArgumentParser(description="Collect features")
parser.add_argument('--dataroot', metavar='D',
        type=str, help='Folder containing raw binaries')
parser.add_argument('--outputdir', metavar='O',
        type=str, help='Output folder which should JSONs for each binary')
parser.add_argument('--compiler', metavar='C',
        type=str, help='Compiler to collect data for <gcc/clang>')
args = parser.parse_args()

#####################################################
# Define constants
#####################################################
# Root for folder containing raw binaries
# RAW_BINARY_FILE_ROOT = "/media/VMs/chinmay_dd/varRecovery/otherProjects/EKLAVYA/binary/x86"
# # Root for directory which will contain output
# DATA_DIR = "/media/VMs/chinmay_dd/varRecovery/stacksyms/stacksymruns/collected_data_clang"

if not os.path.exists(args.outputdir):
    os.makedirs(args.outputdir, exist_ok=True)

# Dont analyze clang files since they have positive offset for variable
# location in DWARF info
def collector(f):
   try:
       if args.compiler and args.compiler not in f:
           print(f"Skipping file {f}")
           return

       outputFile = os.path.join(args.outputdir, f)
       if os.path.isfile(outputFile):
           print(f"File {f} analyzed, returning")
           return

       filePath  = os.path.join(args.dataroot, f)
       functions = parseELF(filePath)
       allLabels = checkLabels(functions)

       with open(os.path.join(args.outputdir, f), 'w') as cf:
           json.dump(allLabels, cf)

       print(f"[+] {f}")
   except Exception as e:
       print(f"[-] Failed {f} : {e}")

#####################################################
# Traverse dir and collect data
#####################################################
for subdir, dirs, files in os.walk(args.dataroot):
    with Pool(processes=50) as pool:
        pool.map(collector, files)
