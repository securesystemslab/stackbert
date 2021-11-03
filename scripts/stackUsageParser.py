import argparse
import json
import os
import logging

parser = argparse.ArgumentParser(description="Collect stack usage information from .su files")
parser.add_argument("--dataroot", metavar="D",
        type=str, help="Folder containing data")
parser.add_argument("--outputdir", metavar="O",
        type=str, help="Output folder which should contain JSONs for each binary")
args = parser.parse_args()

logging.basicConfig(level=logging.WARN)

def parseOneFile(fname):
    result = {}
    with open(fname, "r") as fp:
        lines = fp.readlines()
        for line in lines:
            try:
                func_info, size, size_type = line.split()
                func_name = func_info.split(':')[3]
                result[func_name] = {}
                result[func_name]["max"] = int(size)
            except:
                continue

    return result

if __name__ == "__main__":
    if not os.path.exists(args.outputdir):
        logging.debug("Output directory does not exist, creating")
        os.makedirs(args.outputdir, exist_ok=True)

    # Loop explores top level directories 
    # Each directory is assumed to represent a different binary for which 
    # gcc with -fstack-usage has been ran
    for path in os.listdir(args.dataroot):
        subdir = os.path.join(args.dataroot, path)
        if os.path.isdir(subdir):
            logging.warning(f"Exploring {subdir}")
            allData = {}
            for root, dirs, files in os.walk(subdir):
                for fname in files:
                    if ".su" in fname:
                        logging.debug(f"Parsing file {fname}")
                        result = parseOneFile(os.path.join(root, fname))
                        allData = {**allData, **result}

            outputFilename = path + ".json"
            with open(os.path.join(args.outputdir, outputFilename), "w") as fp:
                json.dump(allData, fp)
