import os
import json
import pdb

import argparse

parser = argparse.ArgumentParser(description="Collect input and output features in a single JSON file")
parser.add_argument('--dataroot', metavar='D',
                    type=str, help='Output folder of mainDriver')
parser.add_argument('--outputdir', metavar='O',
                    type=str, help='Output folder which should contain final JSON')
args = parser.parse_args()

# dataRoot = "stacksymruns/collected_data_layout"

allData = {}
maxX = -1
maxY = -1

distinctSizes = set()
code = set()

for root, dirs, files in os.walk(args.dataroot):
    for f in files:
        with open(os.path.join(root, f)) as fp:
            data = json.load(fp)
            for func in data.keys():
                tempDisas = data[func]["inp"]
                if tempDisas in code or len(tempDisas) < 0:
                    continue

                code.update(str(tempDisas))
                if data[func]["out"] == []:
                    continue

                allData[func + "_" + f] = {}
                allData[func + "_" + f]["X"] = tempDisas
                allData[func + "_" + f]["Y"] = sum(data[func]["out"])
                
                maxX = max(maxX, len(tempDisas))
                maxY = max(maxY, len(data[func]["out"]))

                distinctSizes.update(data[func]["out"])

with open(os.path.join(args.outputdir, "dataset.json"), "w") as fpw:
    json.dump(allData, fpw)

with open(os.path.join(args.outputdir, "datasetSizes.json"), "w") as fpw:
    json.dump(list(distinctSizes), fpw)
